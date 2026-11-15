"""Build the static site's data from the archive, observations and scores: data/site/index.json (points, the
record, the scorecards) and data/site/points/<lid>.json (recent observations, the newest HEFS fan, the newest
model forecasts, the NWS official forecast). The client at app/ reads these files from the data branch.

Run: python site.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from score import LEADS, NOISY, SCORED, read_hefs, read_obs, read_quantiles

# lid: (name, lat, lon). Reservoir inflow points carry their CDEC station; flood gauges their USGS id and
# NWS flood stages (ft: minor, moderate, major) from the NWPS gauge metadata, which is not archived.
RESERVOIRS = {
    "LAMC1": ("Lake Mendocino", 39.197, -123.186), "ORDC1": ("Oroville", 39.540, -121.493),
    "SHDC1": ("Shasta", 40.718, -122.420), "FOLC1": ("Folsom", 38.683, -121.183),
    "NBBC1": ("New Bullards Bar", 39.393, -121.140), "NMSC1": ("New Melones", 37.948, -120.525),
    "FRAC1": ("Millerton", 37.001, -119.705), "EXQC1": ("McClure", 37.585, -120.270),
    "ISAC1": ("Isabella", 35.646, -118.473), "TMDC1": ("Kaweah", 36.415, -119.002),
    "SCSC1": ("Success", 36.057, -118.924), "WSDC1": ("Lake Sonoma", 38.723, -123.010),
    "NDPC1": ("Don Pedro", 37.702, -120.421), "CEGC1": ("Trinity", 40.801, -122.762),
    "INVC1": ("Indian Valley", 39.083, -122.533),
}
GAUGES = {
    "HOPC1": ("Russian River near Hopland", 39.027, -123.131, "11462500", (15, 23, 26)),
    "HEAC1": ("Russian River near Healdsburg", 38.613, -122.836, "11464000", (23, 27, 29)),
    "GUEC1": ("Russian River at Guerneville", 38.499, -122.998, "11467002", (32, 35, 40)),
    "NVRC1": ("Navarro River near Navarro", 39.170, -123.668, "11468000", (23, 30, 34)),
    "FTSC1": ("Eel River near Fort Seward", 40.218, -123.633, "11475000", (70, 80, 90)),
    "SCOC1": ("Eel River near Scotia", 40.491, -124.100, "11477000", (51, 60, 65)),
    "LEGC1": ("South Fork Eel River near Leggett", 39.875, -123.721, "11475800", None),
    "BRGC1": ("Van Duzen River near Bridgeville", 40.480, -123.891, "11478500", (17, 20, 23)),
    "ARCC1": ("Mad River near Arcata", 40.910, -124.061, "11481000", (22, 24, 28)),
    "ORIC1": ("Redwood Creek near Orick", 41.299, -124.051, "11482500", (32, 33, 35)),
    "FTDC1": ("Smith River at Dr Fine Bridge", 41.881, -124.136, "11532650", (33, 36, 39)),
    "MHBC1": ("Cosumnes River at Michigan Bar", 38.500, -121.045, "11335000", (10, 12, 14)),
}
MIN_PAIRS = 20  # a scorecard cell with fewer forecast-days is shown but flagged thin
OBS_DAYS = 120


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
    days = sorted(fc)[: LEADS.stop + 1]
    cols = list(zip(*(percentiles(fc[d]) for d in days)))
    return {"issued": p.stem, "dates": [d.isoformat() for d in days],
            **{k: [round(v) for v in c] for k, c in zip(["p05", "p25", "p50", "p75", "p95"], cols)}}


def models_latest(out: Path, lid: str) -> dict:
    models = {}
    for d in sorted((out / "forecasts").glob("*")) if (out / "forecasts").is_dir() else []:
        p = newest(d / lid, ".csv")
        if p is None:
            continue
        with p.open() as f:
            rows = list(csv.DictReader(f))
        models[d.name] = {"issued": p.stem, "dates": [r["date"] for r in rows],
                          **{k: [round(float(r[k])) for r in rows] for k in ["q05", "q25", "q50", "q75", "q95"] if k in rows[0]}}
    return models


def official_latest(out: Path, lid: str) -> dict | None:
    p = newest(out / "nwps_forecast" / lid, ".gz")
    if p is None:
        return None
    d = json.loads(gzip.decompress(p.read_bytes()))
    flow_scale = 1000 if d.get("secondaryUnits") == "kcfs" else 1
    return {"issued": d.get("issuedTime"), "times": [r["validTime"] for r in d["data"]],
            "stage_ft": [r.get("primary") for r in d["data"]],
            "flow_cfs": [None if r.get("secondary") is None else round(r["secondary"] * flow_scale) for r in d["data"]]}


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
            cells.append({"product": product, "lead" if name == "by_lead" else "lid": key, "n": len(rs),
                          "crps": mean("crps"), "crps_persistence": mean("crps_persistence"),
                          "crps_climatology": mean("crps_climatology"), "cov90": round(mean("in90"), 3),
                          "thin": len(rs) < MIN_PAIRS})
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
        point = {"lid": lid, "kind": "reservoir", "name": name, "lat": lat, "lon": lon, "cdec": SCORED.get(lid),
                 "scored": lid in SCORED, "note": "negative computed inflows at low flow; archived, not scored" if lid in NOISY else None}
        points.append(point)
        (site / "points" / f"{lid}.json").write_text(json.dumps({
            **point, "obs": [[d.isoformat(), v] for d, v in obs], "hefs": hefs_latest(out, lid),
            "models": models_latest(out, lid), "official": None}))
    for lid, (name, lat, lon, usgs, stages) in GAUGES.items():
        files = list((out / "hefs_daily" / lid).glob("*.gz")) if (out / "hefs_daily" / lid).is_dir() else []
        archive_days |= {p.stem[:8] for p in files}
        point = {"lid": lid, "kind": "gauge", "name": name, "lat": lat, "lon": lon, "usgs": usgs, "scored": False,
                 "flood_stages_ft": stages, "note": "forecasts archived; observed flow and scoring not yet wired"}
        points.append(point)
        (site / "points" / f"{lid}.json").write_text(json.dumps({
            **point, "obs": [], "hefs": hefs_latest(out, lid), "models": models_latest(out, lid),
            "official": official_latest(out, lid)}))
    index = {"built": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "record_start": min(archive_days) if archive_days else None,
             "archive_days": len(archive_days), "leads": list(LEADS), "min_pairs": MIN_PAIRS, "points": points,
             "scores": scorecards(out)}
    (site / "index.json").write_text(json.dumps(index))
    return index


if __name__ == "__main__":
    idx = build(Path(sys.argv[1] if len(sys.argv) > 1 else "data"), datetime.now(timezone.utc))
    print(f"site: {len(idx['points'])} points, record since {idx['record_start']}, {idx['archive_days']} archive days, "
          f"{len(idx['scores']['by_lead'])} scorecard cells")
