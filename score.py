"""Score the archived reservoir-inflow forecasts against CDEC observed daily inflow (sensor 76), with
persistence and day-of-year climatology as baselines. Products: the HEFS ensemble (data/hefs_daily) and any
model under data/forecasts/<model>/<lid>/<issue date>.csv (date,lead,q05,...), scored as an ensemble of its
quantiles. Every scored forecast day is one row of the ledger; the pooled table is printed.

Run: python score.py [out_dir]   (default: data/)
     writes out/cdec_inflow/<station>.csv (date,cfs; full record, refreshed every run because CDEC
     revises values) and out/scores/inflow_daily.csv
"""

from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from archive import INFLOW, fetch
from contract import check_forecast

NOISY = {"WSDC1", "NDPC1", "CEGC1", "INVC1"}  # archived, not scored: negative computed inflows at low flow
SCORED = {lid: sta for lid, sta in INFLOW.items() if sta and lid not in NOISY}
CDEC = (
    "https://cdec.water.ca.gov/dynamicapp/req/CSVDataServlet?Stations={sta}&SensorNums=76"
    "&dur_code=D&Start=1980-10-01&End={end:%Y-%m-%d}"
)
LEADS = range(1, 15)
MIN_CLIM_YEARS = 10


def update_obs(out: Path, now: datetime) -> int:
    """Rewrite out/cdec_inflow/<sta>.csv from CDEC. Returns the number of stations that failed."""
    d = out / "cdec_inflow"
    d.mkdir(parents=True, exist_ok=True)
    failed = 0
    for sta in filter(None, INFLOW.values()):
        body = fetch(CDEC.format(sta=sta, end=now))
        if body is None or not body.startswith(b"STATION_ID"):
            failed += 1
            print(f"BAD PAYLOAD cdec {sta}", file=sys.stderr)
            continue
        rows = csv.DictReader(body.decode().splitlines())
        with (d / f"{sta}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "cfs"])
            for r in rows:
                if r["VALUE"] != "---":  # CDEC's missing marker
                    t = r["DATE TIME"]
                    w.writerow([f"{t[:4]}-{t[4:6]}-{t[6:8]}", r["VALUE"]])
    return failed


def read_obs(path: Path) -> dict[date, float]:
    with path.open() as f:
        return {date.fromisoformat(d): float(v) for d, v in list(csv.reader(f))[1:]}


def read_hefs(path: Path) -> dict[date, list[float]]:
    """{day: members in cfs}. A row stamped 12Z is the mean of the 24 hours before it, 04:00 to 04:00 Pacific
    standard time, so it is keyed by the day before its stamp: the Pacific day that holds 20 of those hours and
    the day CDEC's daily value describes. The first day is the day before the issue (all members equal the
    analysis). CNRFC writes -999 for a missing value; those are left out, a day with nothing else is absent, and
    a file whose first row is missing gives nothing, because its issue day is read from that row."""
    rows = {}
    for line in gzip.decompress(path.read_bytes()).decode().splitlines()[2:]:  # 2 header rows
        f = line.split(",")
        members = [float(x) * 1000 for x in f[1:] if x and float(x) != -999]  # kcfs -> cfs
        if members:
            rows[date.fromisoformat(f[0][:10]) - timedelta(days=1)] = members
        elif not rows:
            return {}
    return rows


def read_quantiles(path: Path) -> dict[date, list[float]]:
    """{day: quantile values in cfs} from a model forecast CSV (date, lead, q05, q25, ...)."""
    with path.open() as f:
        rows = list(csv.reader(f))
    return {date.fromisoformat(r[0]): [float(x) for x in r[2:]] for r in rows[1:]}


def forecasts(out: Path, lid: str) -> list[tuple[str, date, dict[date, list[float]]]]:
    """(product, issue day, {day: members}) for every archived forecast of lid; one per product and issue day."""
    latest = {}  # the newest archived HEFS file per issue day wins
    for p in sorted((out / "hefs_daily" / lid).glob("*.gz")):
        fc = read_hefs(p)
        if fc:  # a file of missing values holds no forecast
            latest[("hefs", min(fc) + timedelta(days=1))] = fc  # the first row is the day before the issue
    for p in sorted((out / "forecasts").glob(f"*/{lid}/*.csv")):
        errors = check_forecast(p)
        if errors:  # a file that breaks the contract is left out of the record, and said
            print(f"BAD FORECAST {p.relative_to(out)}: {errors[0]}", file=sys.stderr)
            continue
        latest[(p.parent.parent.name, date.fromisoformat(p.stem))] = read_quantiles(p)
    return [(product, issue, fc) for (product, issue), fc in latest.items()]


def crps(members: list[float], y: float) -> float:
    """Fair ensemble CRPS (Hersbach 2000): E|X-y| - 0.5 E|X-X'| with the n/(n-1) correction.
    E|X-X'| over all n^2 pairs is computed from the sorted members in O(n)."""
    xs = sorted(members)
    n = len(xs)
    spread = 2 * sum((2 * i - n - 1) * x for i, x in enumerate(xs, 1)) / (n * n)
    return sum(abs(x - y) for x in xs) / n - 0.5 * spread * n / max(n - 1, 1)


def score(out: Path) -> list[dict]:
    rows = []
    for lid, sta in SCORED.items():
        obs_path = out / "cdec_inflow" / f"{sta}.csv"
        if not obs_path.exists():
            continue
        obs = read_obs(obs_path)
        by_doy = defaultdict(list)
        for d, v in obs.items():
            if v >= 0:
                by_doy[(d.month, d.day)].append((d.year, v))
        for product, issue, fc in forecasts(out, lid):
            last = obs.get(issue - timedelta(days=1))  # the newest complete day when the run was issued
            for lead in LEADS:
                day = issue + timedelta(days=lead)
                y = obs.get(day)
                clim = [v for yr, v in by_doy[(day.month, day.day)] if yr < issue.year]
                if y is None or y < 0 or last is None or last < 0 or day not in fc or len(clim) < MIN_CLIM_YEARS:
                    continue
                m = sorted(fc[day])
                rows.append(
                    {
                        "product": product,
                        "lid": lid,
                        "issue": issue,
                        "lead": lead,
                        "obs_cfs": y,
                        "crps": round(crps(m, y), 1),
                        "crps_persistence": round(abs(last - y), 1),
                        "crps_climatology": round(crps(clim, y), 1),
                        "in90": int(m[round(0.05 * (len(m) - 1))] <= y <= m[round(0.95 * (len(m) - 1))]),
                    }
                )
    return rows


def main(out: Path) -> int:
    now = datetime.now(UTC)
    failed = update_obs(out, now)
    rows = score(out)
    path = out / "scores" / "inflow_daily.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["product", "lid", "issue", "lead", "obs_cfs", "crps", "crps_persistence", "crps_climatology", "in90"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    print(f"{now:%Y-%m-%dT%H:%MZ} scored {len(rows)} forecast-days, {failed} stations failed")
    print("product                 lead     n  crps  crps_pers  crps_clim  cov90")
    for product in sorted({x["product"] for x in rows}):
        for lead in LEADS:
            r = [x for x in rows if x["lead"] == lead and x["product"] == product]
            if r:
                mean = lambda k: sum(x[k] for x in r) / len(r)
                print(
                    f"{product:22s} {lead:4d} {len(r):5d} {mean('crps'):5.0f} {mean('crps_persistence'):10.0f} "
                    f"{mean('crps_climatology'):10.0f} {mean('in90'):6.2f}"
                )
    return 1 if failed > len(SCORED) // 2 else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
