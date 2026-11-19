"""Build the static site's data from the archive, observations and scores: data/site/index.json (points, the
record, the scorecards) and data/site/points/<lid>.json (recent observations, the newest HEFS fan, the newest
model forecasts, the NWS official forecast, the weather panel, the week's hourly flow and the flood categories). The client at app/ reads these files from the data branch.

Run: python site.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ar_scale import IVT_AR_THRESHOLD, classify_ar
from contract import check_forecast, read_manifest
from ivt_field import load as load_ivt
from points import GAUGES, RESERVOIRS
from score import LEADS, NOISY, SCORED, read_hefs, read_obs

MIN_PAIRS = 20  # a scorecard cell with fewer forecast-days is shown but flagged thin
OBS_DAYS = 120
WEATHER_PAST_DAYS = 7
IVT_PAST_HOURS = 48
STALE_HOURS = 48  # a model whose newest issue is older than this has stopped issuing and is not drawn
# The past forecasts drawn over a gauge's observed hours: at each hour, the newest forecast made at least this
# many hours before it. The page offers the leads as a switch, the first one shown.
TRACE_LEADS = [(1, "1 h ahead"), (6, "6 h ahead"), (24, "24 h ahead")]
TRACE_HOURS = 7 * 24
QUANTILES = ["q05", "q25", "q50", "q75", "q95"]
# The colour steps of the IVT map: the peak-IVT thresholds of the AR scale (ar_scale.py), from the floor of AR
# conditions up. Below the first step the map shows nothing.
IVT_STEPS = [(250, "#3f73d8"), (500, "#35b3a0"), (750, "#f1c642"), (1000, "#f08a3c"), (1250, "#e2457c")]
SOIL_COLOURS = ["--cool", "--ml", "--warn"]  # soil layers, in the order the files list them
WEATHER_COLOURS = {
    "GFS": "--cool",
    "ECMWF": "--ml",
    "ICON": "--warn",
    "NBM": "--official",
}  # tokens in app/src/index.css


def percentiles(members: list[float], qs=(0.05, 0.25, 0.5, 0.75, 0.95)) -> list[float]:
    m = sorted(members)
    return [m[round(q * (len(m) - 1))] for q in qs]


def newest(d: Path, suffix: str) -> Path | None:
    files = sorted(d.glob(f"*{suffix}")) if d.is_dir() else []
    return files[-1] if files else None


def hefs_latest(out: Path, lid: str) -> dict | None:
    p = newest(out / "hefs_daily" / lid, ".gz")
    if p is None:
        return None
    fc = read_hefs(p)
    days = sorted(fc)[1 : LEADS.stop + 1]  # from the issue day on: the day before it is the analysis, already observed
    if not days:  # a file of missing values: no fan
        return None
    cols = list(zip(*(percentiles(fc[d]) for d in days)))
    return {
        "issued": p.stem,
        "dates": [d.isoformat() for d in days],
        **{k: [round(v) for v in c] for k, c in zip(["p05", "p25", "p50", "p75", "p95"], cols)},
    }


def issued_at(p: Path) -> datetime:
    """The issue time of a model forecast file, from its name: a day (at 00Z) or an hour."""
    return datetime.strptime(p.stem, "%Y-%m-%dT%HZ" if "T" in p.stem else "%Y-%m-%d").replace(tzinfo=UTC)


def models_latest(out: Path, lid: str, now: datetime) -> dict:
    """The newest forecast of each model that still issues: one whose newest issue is under STALE_HOURS old."""
    models = {}
    for d in sorted((out / "forecasts").glob("*")) if (out / "forecasts").is_dir() else []:
        files = sorted((d / lid).glob("*.csv")) if (d / lid).is_dir() else []
        p = next((f for f in reversed(files) if not check_forecast(f)), None)  # the newest that holds the contract
        if p is None or now - issued_at(p) > timedelta(hours=STALE_HOURS):
            continue
        with p.open() as f:
            rows = list(csv.DictReader(f))
        hourly = "time" in rows[0]  # an hourly product: each value is drawn at its hour, a daily one at its day
        models[d.name] = {
            "issued": p.stem,
            "dates": [r["time" if hourly else "date"] for r in rows],
            "first": "next hour" if hourly else "day 1",  # what the tile calls the first value
            **{k: [round(float(r[k])) for r in rows] for k in ["q05", "q25", "q50", "q75", "q95"] if k in rows[0]},
            "manifest": read_manifest(d / "MODEL.json"),
        }
    return models


def past_forecasts(out: Path, lid: str, now: datetime) -> dict | None:
    """What each product said about the hours already past, for a gauge: at each of the last TRACE_HOURS hours,
    and for each lead of TRACE_LEADS, the 5 to 95% quantiles of the newest forecast made at least that many
    hours before the hour. HEFS counts from the time hapi archived it, which is when it was known to be out;
    a model from its issue hour. None when no product has a past hour."""
    start = now - timedelta(hours=TRACE_HOURS)
    fans: dict[str, dict[int, dict[datetime, list[float]]]] = {}

    def keep(product: str, known: datetime, rows: list[tuple[datetime, list[float]]]):
        for lead, _ in TRACE_LEADS:
            for t, qs in rows:
                if start <= t <= now and t - known >= timedelta(hours=lead):
                    fans.setdefault(product, {}).setdefault(lead, {})[t] = qs  # files come oldest first: newest wins

    for p in sorted((out / "hefs_hourly" / lid).glob("*.gz")) if (out / "hefs_hourly" / lid).is_dir() else []:
        known = datetime.strptime(p.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        rows = []
        for line in gzip.decompress(p.read_bytes()).decode().splitlines()[2:]:
            f = line.split(",")
            t = datetime.strptime(f[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            members = [float(x) * 1000 for x in f[1:] if x and float(x) != -999]  # kcfs -> cfs; -999 is missing
            if members and start <= t <= now and t - known >= timedelta(hours=TRACE_LEADS[0][0]):
                rows.append((t, percentiles(members)))
        keep("HEFS", known, rows)
    for d in sorted((out / "forecasts").glob("*")) if (out / "forecasts").is_dir() else []:
        for p in sorted((d / lid).glob("*T*Z.csv")) if (d / lid).is_dir() else []:  # hourly products only
            if check_forecast(p):
                continue
            with p.open() as f:
                rows = [
                    (
                        datetime.strptime(r["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC),
                        [float(r[q]) for q in QUANTILES],
                    )
                    for r in csv.DictReader(f)
                ]
            keep(d.name, issued_at(p), rows)
    if not fans:
        return None
    return {
        "leads": [{"hours": h, "label": label} for h, label in TRACE_LEADS],
        "fans": [
            {
                "product": product,
                "lead": lead,
                "times": [f"{t:%Y-%m-%dT%H:%MZ}" for t in sorted(series)],
                **{q: [round(series[t][k]) for t in sorted(series)] for k, q in enumerate(QUANTILES)},
            }
            for product, by_lead in fans.items()
            for lead, series in sorted(by_lead.items())
        ],
    }


def official_latest(out: Path, lid: str) -> dict | None:
    p = newest(out / "nwps_forecast" / lid, ".gz")
    if p is None:
        return None
    d = json.loads(gzip.decompress(p.read_bytes()))
    flow_scale = 1000 if d.get("secondaryUnits") == "kcfs" else 1
    return {
        "issued": d.get("issuedTime"),
        "times": [r["validTime"] for r in d["data"]],
        "stage_ft": [r.get("primary") for r in d["data"]],
        "flow_cfs": [None if r.get("secondary") is None else round(r["secondary"] * flow_scale) for r in d["data"]],
    }


def weather_window(out: Path, lid: str) -> tuple[Path, dict] | None:
    """(the newest archived file, the merged weather) from every file of the last WEATHER_PAST_DAYS days. Each
    hour takes the value of the newest file that has one, so past hours come from the run just before them
    and future hours from the newest run. The merged dict has a file's shape, with IVT under its model."""
    files = sorted((out / "weather" / lid).glob("*.gz")) if (out / "weather" / lid).is_dir() else []
    if not files:
        return None
    since = datetime.strptime(files[-1].stem, "%Y%m%dT%H%M%SZ") - timedelta(days=WEATHER_PAST_DAYS)
    hours: dict[str, dict[tuple[str, str], float | None]] = {}
    keys: dict[tuple[str, str], None] = {}  # (variable, model), in the order the newest files list them
    for p in reversed([f for f in files if f.stem >= f"{since:%Y%m%dT%H%M%SZ}"]):
        w = json.loads(gzip.decompress(p.read_bytes()))
        columns = {("ivt", "GFS"): w["ivt"]}
        columns.update({(var, m): v for var, group in w.items() if isinstance(group, dict) for m, v in group.items()})
        keys.update(dict.fromkeys(columns))
        for i, t in enumerate(w["times"]):
            cell = hours.setdefault(t, {})
            for k, v in columns.items():
                if cell.get(k) is None:  # files run newest first: an hour keeps the newest value it was given
                    cell[k] = v[i]
    times = sorted(t for t in hours if t >= f"{since:%Y-%m-%dT%H:00}")
    merged: dict = {"times": times}
    for var, m in keys:
        merged.setdefault(var, {})[m] = [hours[t].get((var, m)) for t in times]
    return files[-1], merged


def weather_latest(out: Path, lid: str) -> dict | None:
    """The weather panel for a point, ready to draw: tiles and chart series with their labels, units and
    colours (names of the page's CSS tokens). The page draws whatever is here, so changing what it says or
    shows is an edit to this function. The charts cover the past week and the forecast (weather_window);
    the tiles, the AR scale and the running totals start at the newest file's issue hour."""
    found = weather_window(out, lid)
    if found is None:
        return None
    p, w = found
    times = w["times"]
    issue_hour = f"{p.stem[:4]}-{p.stem[4:6]}-{p.stem[6:8]}T{p.stem[9:11]}:00"  # the stem is the UTC fetch time
    start = next((i for i, t in enumerate(times) if t >= issue_hour), None)
    if start is None:  # the newest file is older than its own forecast: nothing current to show
        return None
    ahead = times[start:]
    when = lambda t: f"{datetime.fromisoformat(t):%b} {int(t[8:10])} {t[11:13]}Z"
    convert = lambda var, f: {m: [None if x is None else f(x) for x in v] for m, v in w.get(var, {}).items()}
    lines = lambda group: [
        {"label": m, "colour": WEATHER_COLOURS.get(m, "--official"), "values": v} for m, v in group.items()
    ]
    tiles = []

    ivt = w["ivt"]["GFS"]
    ar = classify_ar([v or 0 for v in ivt[start:]], 1.0, ahead)  # an hour with no IVT counts as no transport
    if ar.onset_time is None:
        note = f"peak IVT {ar.max_ivt:.0f} kg/m/s, below {IVT_AR_THRESHOLD:.0f}"
    else:
        arrival = "under way" if ar.onset_time == ahead[0] else f"arrives {when(ar.onset_time)}"
        note = (
            f"peak {ar.max_ivt:.0f} kg/m/s · {arrival} · {ar.duration_hours:.0f} h above "
            f"{IVT_AR_THRESHOLD:.0f} · {ar.impact}"
        )
    tiles.append(
        {
            "label": "AR scale, GFS",
            "value": ar.label,
            "note": note,
            "flag": {2: "warn", 3: "warn", 4: "danger", 5: "danger"}.get(ar.category),
        }
    )

    precip = convert("precip_mm", lambda x: x / 25.4)  # inches
    # a model that stops short has no total
    totals = {m: sum(x for x in v[start:] if x is not None) for m, v in precip.items() if None not in v[start:]}
    if totals:
        lead = next(iter(totals))
        tiles.append(
            {
                "label": f"Precip through {when(times[-1])[:-4]}, {lead}",
                "value": f"{totals[lead]:.2f} in",
                "note": " · ".join(f"{m} {t:.2f}" for m, t in totals.items() if m != lead),
                "flag": None,
            }
        )

    freezing = convert("freezing_m", lambda x: round(x * 3.28084, -1))  # feet
    for m, v in freezing.items():
        soon = [x for x in v[start : start + 72] if x is not None]
        if soon:
            tiles.append(
                {
                    "label": "Freezing level, next 72 h",
                    "value": f"{min(soon):,.0f} to {max(soon):,.0f} ft",
                    "note": m,
                    "flag": None,
                }
            )
            break

    def running(xs: list) -> list:  # running total from the issue hour; the line ends where the model does
        total, out_ = 0.0, [None] * start
        for x in xs[start:]:
            total = None if x is None or total is None else total + x
            out_.append(None if total is None else round(total, 2))
        return out_

    def bars(group: dict, digits: int) -> dict:  # the first model's hourly amounts, hanging from the top
        return {
            "bars": {
                "label": f"{m}, hourly",
                "colour": WEATHER_COLOURS[m],
                "values": [None if x is None else round(x, digits) for x in v],
            }
            for m, v in list(group.items())[:1]
        }

    charts = [
        {
            "id": "precip",
            "label": "Precip",
            "unit": "in",
            "digits": 2,
            "series": [
                {"label": f"{m}, running total", "colour": WEATHER_COLOURS[m], "values": running(v)}
                for m, v in precip.items()
            ],
            **bars(precip, 3),
        },
        {
            "id": "ivt",
            "label": "IVT",
            "unit": "kg/m/s",
            "digits": 0,
            "line": {"value": IVT_AR_THRESHOLD, "label": f"AR conditions, {IVT_AR_THRESHOLD:.0f} kg/m/s"},
            "series": [{"label": "GFS IVT", "colour": WEATHER_COLOURS["GFS"], "values": ivt}],
        },
        {"id": "freezing", "label": "Freezing level", "unit": "ft", "digits": 0, "series": lines(freezing)},
        {
            "id": "temperature",
            "label": "Temperature",
            "unit": "°F",
            "digits": 0,
            "line": {"value": 32, "label": "freezing, 32 °F"},
            "series": lines(convert("temperature_c", lambda x: round(x * 9 / 5 + 32, 1))),
        },
        {
            "id": "snow",
            "label": "Snow",
            "unit": "in",
            "digits": 1,
            "series": [
                {**s, "label": f"{s['label']}, depth"}
                for s in lines(convert("snow_depth_m", lambda x: round(x * 39.3701, 1)))
            ],
            **bars(convert("snowfall_cm", lambda x: x / 2.54), 2),
        },
        {
            "id": "soil",
            "label": "Soil moisture",
            "unit": "%",
            "digits": 0,
            "series": [
                {"label": m, "colour": SOIL_COLOURS[i % len(SOIL_COLOURS)], "values": v}
                for i, (m, v) in enumerate(convert("soil_m3m3", lambda x: round(x * 100, 1)).items())
            ],
        },
        {
            "id": "gusts",
            "label": "Wind gusts",
            "unit": "mph",
            "digits": 0,
            "series": lines(convert("gust_kmh", lambda x: round(x * 0.621371))),
        },
    ]
    return {
        "issued": p.stem,
        "times": times,
        "tiles": tiles,
        "charts": [c for c in charts if c["series"]],
        "note": "Open-Meteo forecasts: GFS, ECMWF IFS, ICON, NBM. IVT from GFS winds and humidity, 1000 to 300 hPa; "
        "AR scale after Ralph et al. (2019), on hourly IVT. Past hours show each model's newest archived value "
        f"for that hour. Hours are UTC; fetched {issue_hour[:10]} {p.stem[9:11]}:{p.stem[11:13]}Z.",
    }


def ivt_page(out: Path, now: datetime) -> dict | None:
    """The IVT field for the map, ready to draw: one frame of eastward and northward IVT per valid time, with
    its label, the frame that is now, and the legend. The frames are the hour 0 fields of the cycles saved
    over the IVT_PAST_HOURS before the newest full cycle, then that cycle's forecast. None before ivt_field.py
    has saved a full cycle."""
    cycles = [load_ivt(p) for p in sorted((out / "ivt_gfs").glob("*.gz"))[-(IVT_PAST_HOURS // 6 + 4) :]]
    full = [c for c in cycles if len(c["hours"]) > 1]
    if not full:
        return None
    newest = full[-1]
    start = lambda c: datetime.strptime(c["cycle"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    frames = {}  # valid time -> (u, v); the newest cycle is put last, so its hours win
    for c in [c for c in cycles if timedelta(0) < start(newest) - start(c) <= timedelta(hours=IVT_PAST_HOURS)]:
        frames[start(c)] = (c["u"][0], c["v"][0])
    for k, hour in enumerate(newest["hours"]):
        frames[start(newest) + timedelta(hours=hour)] = (newest["u"][k], newest["v"][k])
    times = sorted(frames)
    return {
        "issued": f"GFS {start(newest):%Y-%m-%d %H}Z",
        "source": "GFS 1 degree, NOAA; IVT from wind and humidity, 1000 to 300 hPa",
        "unit": "kg/m/s",
        **{k: newest[k] for k in ("north", "south", "west", "east", "nx", "ny")},
        "times": [f"{t:%Y-%m-%dT%H:%MZ}" for t in times],
        "labels": [f"{t:%b} {t.day} {t:%H}Z" for t in times],
        "now": max((i for i, t in enumerate(times) if t <= now), default=0),
        "u": [frames[t][0] for t in times],
        "v": [frames[t][1] for t in times],
        "legend": [{"from": level, "colour": colour, "label": f"{level:,}"} for level, colour in IVT_STEPS],
        "floor": f"AR conditions from {IVT_AR_THRESHOLD:.0f} kg/m/s",
    }


def live_latest(out: Path, lid: str) -> dict | None:
    """What live.py fetched for the point: the week's hourly flow and, at a gauge, its flood categories."""
    p = out / "live" / f"{lid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def scorecards(out: Path) -> dict:
    path = out / "scores" / "inflow_daily.csv"
    if not path.exists():
        return {"by_lead": [], "by_point": []}
    with path.open() as f:
        rows = list(csv.DictReader(f))
    groups = {"by_lead": defaultdict(list), "by_point": defaultdict(list)}
    for r in rows:
        groups["by_lead"][(r["product"], int(r["lead"]))].append(r)
        groups["by_point"][(r["product"], r["lid"])].append(r)
    out_ = {}
    for name, g in groups.items():
        cells = []
        for (product, key), rs in sorted(g.items()):
            mean = lambda k: round(sum(float(x[k]) for x in rs) / len(rs), 1)
            cells.append(
                {
                    "product": product,
                    "lead" if name == "by_lead" else "lid": key,
                    "n": len(rs),
                    "crps": mean("crps"),
                    "crps_persistence": mean("crps_persistence"),
                    "crps_climatology": mean("crps_climatology"),
                    "cov90": round(mean("in90"), 3),
                    "thin": len(rs) < MIN_PAIRS,
                }
            )
        out_[name] = cells
    return out_


def build(out: Path, now: datetime) -> dict:
    site = out / "site"
    (site / "points").mkdir(parents=True, exist_ok=True)
    points = []
    archive_days = set()
    for lid, (name, lat, lon) in RESERVOIRS.items():
        files = list((out / "hefs_daily" / lid).glob("*.gz")) if (out / "hefs_daily" / lid).is_dir() else []
        archive_days |= {p.stem[:8] for p in files}
        obs_path = out / "cdec_inflow" / f"{SCORED.get(lid, '')}.csv"
        obs = sorted(read_obs(obs_path).items())[-OBS_DAYS:] if obs_path.exists() else []
        point = {
            "lid": lid,
            "kind": "reservoir",
            "name": name,
            "lat": lat,
            "lon": lon,
            "cdec": SCORED.get(lid),
            "scored": lid in SCORED,
            "note": "negative computed inflows at low flow; archived, not scored" if lid in NOISY else None,
        }
        points.append(point)
        (site / "points" / f"{lid}.json").write_text(
            json.dumps(
                {
                    **point,
                    "obs": [[d.isoformat(), v] for d, v in obs],
                    "hefs": hefs_latest(out, lid),
                    "models": models_latest(out, lid, now),
                    "official": None,
                    "weather": weather_latest(out, lid),
                    "live": live_latest(out, lid),
                    "alerts": [],
                }
            )
        )
    for lid, (name, lat, lon, usgs) in GAUGES.items():
        files = list((out / "hefs_daily" / lid).glob("*.gz")) if (out / "hefs_daily" / lid).is_dir() else []
        archive_days |= {p.stem[:8] for p in files}
        point = {
            "lid": lid,
            "kind": "gauge",
            "name": name,
            "lat": lat,
            "lon": lon,
            "usgs": usgs,
            "scored": False,
            "note": "forecasts archived; daily scoring not yet wired",
        }
        points.append(point)
        live = live_latest(out, lid) or {}
        (site / "points" / f"{lid}.json").write_text(
            json.dumps(
                {
                    **point,
                    "obs": [],
                    "hefs": hefs_latest(out, lid),
                    "models": models_latest(out, lid, now),
                    "official": official_latest(out, lid),
                    "weather": weather_latest(out, lid),
                    "live": {k: v for k, v in live.items() if k != "alerts"} or None,
                    "alerts": live.get("alerts", []),
                    "past": past_forecasts(out, lid, now),
                }
            )
        )
    index = {
        "built": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_start": min(archive_days) if archive_days else None,
        "archive_days": len(archive_days),
        "leads": list(LEADS),
        "min_pairs": MIN_PAIRS,
        "points": points,
        "scores": scorecards(out),
    }
    (site / "index.json").write_text(json.dumps(index))
    field = ivt_page(out, now)
    if field:
        (site / "ivt.json").write_text(json.dumps(field, separators=(",", ":")))
    return index


if __name__ == "__main__":
    idx = build(Path(sys.argv[1] if len(sys.argv) > 1 else "data"), datetime.now(UTC))
    print(
        f"site: {len(idx['points'])} points, record since {idx['record_start']}, {idx['archive_days']} archive days, "
        f"{len(idx['scores']['by_lead'])} scorecard cells"
    )
