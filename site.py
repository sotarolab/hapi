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
from datetime import UTC, datetime
from pathlib import Path

from ar_scale import IVT_AR_THRESHOLD, classify_ar
from contract import check_forecast, read_manifest
from points import GAUGES, RESERVOIRS
from score import LEADS, NOISY, SCORED, read_hefs, read_obs

MIN_PAIRS = 20  # a scorecard cell with fewer forecast-days is shown but flagged thin
OBS_DAYS = 120
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


def models_latest(out: Path, lid: str) -> dict:
    models = {}
    for d in sorted((out / "forecasts").glob("*")) if (out / "forecasts").is_dir() else []:
        files = sorted((d / lid).glob("*.csv")) if (d / lid).is_dir() else []
        p = next((f for f in reversed(files) if not check_forecast(f)), None)  # the newest that holds the contract
        if p is None:
            continue
        with p.open() as f:
            rows = list(csv.DictReader(f))
        models[d.name] = {
            "issued": p.stem,
            "dates": [r["date"] for r in rows],
            **{k: [round(float(r[k])) for r in rows] for k in ["q05", "q25", "q50", "q75", "q95"] if k in rows[0]},
            "manifest": read_manifest(d / "MODEL.json"),
        }
    return models


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


def weather_latest(out: Path, lid: str) -> dict | None:
    """The weather panel for a point, ready to draw: tiles and chart series with their labels, units and
    colours (names of the page's CSS tokens). The page draws whatever is here, so changing what it says or
    shows is an edit to this function. Built from the newest file weather.py archived, from its issue hour on."""
    p = newest(out / "weather" / lid, ".gz")
    if p is None:
        return None
    w = json.loads(gzip.decompress(p.read_bytes()))
    issue_hour = f"{p.stem[:4]}-{p.stem[4:6]}-{p.stem[6:8]}T{p.stem[9:11]}:00"  # the stem is the UTC fetch time
    start = next((i for i, t in enumerate(w["times"]) if t >= issue_hour), None)
    if start is None:  # the newest file is older than its own forecast: nothing current to show
        return None
    times = w["times"][start:]
    when = lambda t: f"{datetime.fromisoformat(t):%b} {int(t[8:10])} {t[11:13]}Z"
    tiles = []

    ivt = w["ivt"][start:]
    ar = classify_ar([v or 0 for v in ivt], 1.0, times)  # an hour with no IVT counts as no transport
    if ar.onset_time is None:
        note = f"peak IVT {ar.max_ivt:.0f} kg/m/s, below {IVT_AR_THRESHOLD:.0f}"
    else:
        arrival = "under way" if ar.onset_time == times[0] else f"arrives {when(ar.onset_time)}"
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

    precip = {m: [None if x is None else x / 25.4 for x in v[start:]] for m, v in w["precip_mm"].items()}  # inches
    totals = {
        m: sum(x for x in v if x is not None) for m, v in precip.items() if None not in v
    }  # a model that stops short has no total
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

    freezing = {
        m: [None if x is None else round(x * 3.28084, -1) for x in v[start:]] for m, v in w["freezing_m"].items()
    }  # feet
    for m, v in freezing.items():
        soon = [x for x in v[:72] if x is not None]
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

    def running(xs: list) -> list:  # running total; the line ends where the model does
        total, out_ = 0.0, []
        for x in xs:
            total = None if x is None or total is None else total + x
            out_.append(None if total is None else round(total, 2))
        return out_

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
            **(
                {
                    "bars": {
                        "label": f"{m}, hourly",
                        "colour": WEATHER_COLOURS[m],
                        "values": [None if x is None else round(x, 3) for x in v],
                    }
                    for m, v in list(precip.items())[:1]
                }
            ),
        },
        {
            "id": "ivt",
            "label": "IVT",
            "unit": "kg/m/s",
            "digits": 0,
            "line": {"value": IVT_AR_THRESHOLD, "label": f"AR conditions, {IVT_AR_THRESHOLD:.0f} kg/m/s"},
            "series": [{"label": "GFS IVT", "colour": WEATHER_COLOURS["GFS"], "values": ivt}],
        },
        {
            "id": "freezing",
            "label": "Freezing level",
            "unit": "ft",
            "digits": 0,
            "series": [{"label": m, "colour": WEATHER_COLOURS[m], "values": v} for m, v in freezing.items()],
        },
    ]
    return {
        "issued": p.stem,
        "times": times,
        "tiles": tiles,
        "charts": [c for c in charts if c["series"]],
        "note": "Open-Meteo forecasts: GFS, ECMWF IFS, ICON, NBM. IVT from GFS winds and humidity, 1000 to 300 hPa; "
        f"AR scale after Ralph et al. (2019), on hourly IVT. Hours are UTC; fetched {issue_hour[:10]} {p.stem[9:11]}:{p.stem[11:13]}Z.",
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
                    "models": models_latest(out, lid),
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
                    "models": models_latest(out, lid),
                    "official": official_latest(out, lid),
                    "weather": weather_latest(out, lid),
                    "live": {k: v for k, v in live.items() if k != "alerts"} or None,
                    "alerts": live.get("alerts", []),
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
    return index


if __name__ == "__main__":
    idx = build(Path(sys.argv[1] if len(sys.argv) > 1 else "data"), datetime.now(UTC))
    print(
        f"site: {len(idx['points'])} points, record since {idx['record_start']}, {idx['archive_days']} archive days, "
        f"{len(idx['scores']['by_lead'])} scorecard cells"
    )
