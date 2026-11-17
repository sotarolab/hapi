"""Archive the official forecasts that cannot be backfilled: CNRFC HEFS ensembles and the
NWS official stage/flow forecast. Observations (USGS, CDEC) can be fetched later, so they are not here.

Run: python archive.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import gzip
import http.client
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# fmt: off
# Reservoir inflow points: CNRFC id -> CDEC station holding observed daily inflow (sensor 76).
# Archive wide, score narrow: WSDC1, NDPC1, CEGC1, INVC1 have negative computed inflows at low flow.
INFLOW = {
    "LAMC1": "COY", "WSDC1": "WRS", "ORDC1": "ORO", "SHDC1": "SHA", "FOLC1": "FOL", "NBBC1": "BUL",
    "NDPC1": "DNP", "NMSC1": "NML", "FRAC1": "MIL", "CEGC1": "CLE", "EXQC1": "EXC", "ISAC1": "ISB",
    "TMDC1": "TRM", "SCSC1": "SCC", "HETC1": None, "INVC1": "INV", "CMPC1": None,
}
# River gauges with NWS flood categories (North Coast plus Cosumnes).
FLOOD = ["HOPC1", "HEAC1", "GUEC1", "NVRC1", "FTSC1", "SCOC1", "LEGC1", "BRGC1", "ARCC1", "ORIC1",
         "FTDC1", "MHBC1"]
# fmt: on

HEFS = "https://www.cnrfc.noaa.gov/csv/{lid}_hefs_csv_{step}.csv"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}/stageflow/forecast"


def sources() -> list[tuple[str, str, str]]:
    """(lid, product, url). Hourly ensembles only where the daily peak matters (flood gauges)."""
    out = [(lid, "hefs_daily", HEFS.format(lid=lid, step="daily")) for lid in [*INFLOW, *FLOOD]]
    out += [(lid, "hefs_hourly", HEFS.format(lid=lid, step="hourly")) for lid in FLOOD]
    out += [(lid, "nwps_forecast", NWPS.format(lid=lid)) for lid in FLOOD]
    return out


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "hapi-archiver"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except (OSError, http.client.HTTPException) as e:  # URLError, timeouts and dropped connections alike
        print(f"FAILED {url}: {e}", file=sys.stderr)
        return None


def save(out: Path, lid: str, product: str, body: bytes, now: datetime) -> Path | None:
    """Write body gzipped under out/product/lid/, unless it equals the newest file already there."""
    d = out / product / lid
    d.mkdir(parents=True, exist_ok=True)
    prev = sorted(d.glob("*.gz"))
    if prev and gzip.decompress(prev[-1].read_bytes()) == body:
        return None
    path = d / f"{now:%Y%m%dT%H%M%SZ}.gz"
    path.write_bytes(gzip.compress(body, mtime=0))  # mtime=0: same content gives the same bytes
    return path


def main(out: Path) -> int:
    now = datetime.now(UTC)
    saved = failed = 0
    for lid, product, url in sources():
        body = fetch(url)
        # CNRFC answers a missing file with an HTML page, so check the payload, not just the status.
        if body is None or not (body.startswith(b"GMT") if product.startswith("hefs") else body[:1] == b"{"):
            failed += 1
            print(f"BAD PAYLOAD {lid} {product}", file=sys.stderr)
            continue
        saved += save(out, lid, product, body, now) is not None
    print(f"{now:%Y-%m-%dT%H:%MZ} saved {saved} new, {failed} failed, of {len(sources())}")
    return 1 if failed > len(sources()) // 2 else 0  # fail loudly only when the source is broadly down


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
