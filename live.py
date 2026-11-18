"""Fetch what changes through the day and is not worth archiving: the hourly observed flow at every point over
the last week (CDEC computed inflow at the reservoirs, the NWS observed series at the flood gauges) and the NWS
flood categories of each gauge in cfs. Rewrites data/live/<lid>.json on every run; site.py copies the file
into the point's page data. The gauges' observed series is also kept for good, under data/gauge_obs/ (`record`).

Run: python live.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from archive import FLOOD, INFLOW, fetch

LIVE_DAYS = 7
WINDOW = 24  # hours in the reservoir mean
CDEC_HOURLY = (
    "https://cdec.water.ca.gov/dynamicapp/req/CSVDataServlet?Stations={sta}&SensorNums=76"
    "&dur_code=H&Start={start:%Y-%m-%d}&End={end:%Y-%m-%d}"
)
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}"
CATEGORIES = ["action", "minor", "moderate", "major"]


def cdec_hourly(body: bytes) -> tuple[list[str], list[float | None]]:
    """(UTC hours, cfs) from CDEC's hourly CSV, a missing hour kept as None so positions are hours.
    CDEC stamps PST all year, so UTC is eight hours later."""
    times, cfs = [], []
    for r in csv.DictReader(body.decode().splitlines()):
        t = datetime.strptime(r["DATE TIME"], "%Y%m%d %H%M") + timedelta(hours=8)
        times.append(t.strftime("%Y-%m-%dT%H:%MZ"))
        cfs.append(None if r["VALUE"] == "---" else float(r["VALUE"]))  # ---: CDEC's missing marker
    return times, cfs


def centred_mean(values: list[float | None], n: int = WINDOW) -> list[float | None]:
    """Mean of the n values around each position (n/2 before, n/2 from it on), so a day's mean sits at the
    middle of that day beside the daily observation. None where the window runs off either end of the series
    or holds fewer than three quarters of its hours."""
    half = n // 2
    out: list[float | None] = []
    for i in range(len(values)):
        window = [v for v in values[i - half : i + half] if v is not None] if half <= i <= len(values) - half else []
        out.append(round(sum(window) / len(window)) if len(window) >= 0.75 * n else None)
    return out


def informative(values: list[float | None]) -> bool:
    """Whether the hourly values say something about the flow: at least two days of them, varying less than
    their mean. CDEC computes hourly inflow from storage change and release, and at a small reservoir one
    storage step is several times the inflow; a 24-hour mean of that is still noise."""
    valid = [v for v in values if v is not None]
    return len(valid) >= 2 * WINDOW and statistics.pstdev(valid) < abs(statistics.fmean(valid))


def nwps_observed(d: dict) -> dict:
    """times, cfs and stage_ft from an NWPS stageflow series (flow comes in kcfs or cfs)."""
    scale = 1000 if d.get("secondaryUnits") == "kcfs" else 1
    rows = d["data"]
    ok = lambda v: None if v is None or v < 0 else v  # NWPS marks a missing value -999
    return {
        "times": [r["validTime"] for r in rows],
        "stage_ft": [ok(r.get("primary")) for r in rows],
        "cfs": [None if ok(r.get("secondary")) is None else round(r["secondary"] * scale) for r in rows],
    }


def rating_flow(rating: list[tuple[float, float]], stage: float) -> int | None:
    """Flow at a stage by linear interpolation in the rating curve; None outside it."""
    below = [p for p in rating if p[0] <= stage]
    above = [p for p in rating if p[0] >= stage]
    if not below or not above:
        return None
    (s0, f0), (s1, f1) = max(below), min(above)
    return round(f0 if s1 == s0 else f0 + (f1 - f0) * (stage - s0) / (s1 - s0))


def alerts(gauge: dict, rating: list[tuple[float, float]]) -> list[dict]:
    """The NWS flood categories as [{label, ft, cfs}], lowest first. NWPS marks an unset value -9999 and
    gives the flows for few gauges; when any is missing every flow is read off the gauge's own NWS rating
    curve, so the set comes from one rating and stays in order."""
    cats = (gauge.get("flood") or {}).get("categories") or {}
    ok = lambda v: None if v is None or v < 0 else v
    levels = [
        (name.capitalize(), ok(c.get("stage")), ok(c.get("flow")))
        for name, c in ((n, cats.get(n) or {}) for n in CATEGORIES)
    ]
    levels = [(label, stage, flow) for label, stage, flow in levels if stage is not None]
    from_rating = any(flow is None for _, _, flow in levels)
    return [
        {"label": label, "ft": stage, "cfs": rating_flow(rating, stage) if from_rating else flow}
        for label, stage, flow in levels
    ]


def since(live: dict, start: str) -> dict:
    """The hourly series from `start` on; anything else in the dict passes through."""
    keep = [i for i, t in enumerate(live["times"]) if t >= start]
    return {
        k: [v[i] for i in keep] if k in ("times", "cfs", "stage_ft") and isinstance(v, list) else v
        for k, v in live.items()
    }


def record(out: Path, lid: str, obs: dict, now: datetime) -> int:
    """Keep a gauge's observed series as a growing record, out/gauge_obs/<lid>/<YYYY-MM-DD>.csv: one row
    (time, cfs, stage_ft, seen) for each value the first time it is seen and each time it changes, `seen` being
    the time of this run. Rows are only ever added, so the first value published for a time stays in the file
    beside its revisions. A file holds one UTC day, so an hourly run rewrites a few kilobytes, not a month.
    Returns the number of rows added."""
    text = lambda v: "" if v is None else f"{v:g}"
    days: dict[str, list[tuple[str, str, str]]] = {}
    for t, cfs, stage in zip(obs["times"], obs["cfs"], obs["stage_ft"]):
        if cfs is not None or stage is not None:
            days.setdefault(t[:10], []).append((t, text(cfs), text(stage)))
    added = 0
    for day, rows in days.items():
        path = out / "gauge_obs" / lid / f"{day}.csv"
        known = {}
        if path.exists():
            with path.open(newline="") as f:
                known = {r[0]: (r[1], r[2]) for r in list(csv.reader(f))[1:]}  # the last row of a time is its value now
        new = [r for r in rows if known.get(r[0]) != (r[1], r[2])]
        if new:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", newline="") as f:
                w = csv.writer(f)
                if not known:
                    w.writerow(["time", "cfs", "stage_ft", "seen"])
                w.writerows([*r, f"{now:%Y-%m-%dT%H:%MZ}"] for r in new)
            added += len(new)
    return added


def update_live(out: Path, now: datetime) -> int:
    """Rewrite out/live/<lid>.json for every point. Returns the number of points that failed."""
    d = out / "live"
    d.mkdir(parents=True, exist_ok=True)
    start = now - timedelta(days=LIVE_DAYS)
    failed = 0
    for lid, sta in INFLOW.items():
        if not sta:
            continue
        body = fetch(CDEC_HOURLY.format(sta=sta, start=start, end=now + timedelta(days=1)))
        if body is None or not body.startswith(b"STATION_ID"):
            failed += 1
            print(f"BAD PAYLOAD cdec hourly {sta}", file=sys.stderr)
            continue
        times, cfs = cdec_hourly(body)
        hourly = [None if v == 0 else v for v in cfs]  # CDEC writes 0 for an hour a component sensor missed
        path = d / f"{lid}.json"
        if not informative(hourly):
            path.unlink(missing_ok=True)
            print(f"left out {lid}: CDEC {sta} hourly inflow is missing or varies more than its mean")
            continue
        live = {
            "source": f"CDEC {sta}, 24-h mean of hourly computed inflow, centred on the hour",
            "times": times,
            "cfs": centred_mean(hourly),
            "stage_ft": None,
        }
        path.write_text(json.dumps(since(live, start.strftime("%Y-%m-%dT%H:%MZ"))))
    for lid in FLOOD:
        bodies = [fetch(NWPS.format(lid=lid) + suffix) for suffix in ("/stageflow/observed", "", "/ratings")]
        try:
            obs, gauge, rating = (json.loads(b or b"") for b in bodies)  # a failed fetch reads as bad JSON
            live = {
                "source": f"NWS observed at {lid}",
                **nwps_observed(obs),
                "alerts": alerts(gauge, [(r["stage"], r["flow"]) for r in rating.get("data", [])]),
            }
        except (KeyError, TypeError, ValueError) as e:
            failed += 1
            print(f"BAD PAYLOAD nwps {lid}: {e}", file=sys.stderr)
            continue
        record(out, lid, live, now)
        (d / f"{lid}.json").write_text(json.dumps(since(live, start.strftime("%Y-%m-%dT%H:%M:%SZ"))))
    return failed


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    n = update_live(out, datetime.now(UTC))
    print(f"live: {len(list((out / 'live').glob('*.json')))} points written, {n} failed")
    sys.exit(1 if n else 0)
