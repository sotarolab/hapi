"""Archive the official forecasts as they are issued: CNRFC HEFS ensembles, the NWS official stage/flow
forecast, and the National Water Model's short-range and medium-range forecasts at the flood gauges. CNRFC also keeps the 12Z HEFS issues since January 2014 as dated zips, which retro.py reads for a
hindcast. Whether the NWS official forecast can be fetched later was not checked, so it is saved here.
Observations (USGS, CDEC) can be fetched later, so they are not here.

Run: python archive.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import gzip
import http.client
import json
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
# The National Water Model at each flood gauge's river reach (its `reachId` in the NWS gauge record), one
# series per request: short range is hourly for 18 hours; medium range holds the mean and the members for 10 days.
NWM = "https://api.water.noaa.gov/nwps/v1/reaches/{reach}/streamflow?series={series}"
# fmt: off
NWM_REACH = {
    "HOPC1": 8269119, "HEAC1": 8272379, "GUEC1": 8273703, "NVRC1": 2665613, "FTSC1": 2706571, "SCOC1": 2704735,
    "LEGC1": 8287256, "BRGC1": 2705477, "ARCC1": 8316811, "ORIC1": 8315607, "FTDC1": 22227058, "MHBC1": 20192498,
}
# fmt: on


def sources() -> list[tuple[str, str, str]]:
    """(lid, product, url). Hourly ensembles only where the daily peak matters (flood gauges)."""
    out = [(lid, "hefs_daily", HEFS.format(lid=lid, step="daily")) for lid in [*INFLOW, *FLOOD]]
    out += [(lid, "hefs_hourly", HEFS.format(lid=lid, step="hourly")) for lid in FLOOD]
    out += [(lid, "nwps_forecast", NWPS.format(lid=lid)) for lid in FLOOD]
    out += [
        (lid, f"nwm_{series}", NWM.format(reach=NWM_REACH[lid], series=series))
        for series in ("short_range", "medium_range")
        for lid in FLOOD
    ]
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


def forecast_only(body: bytes) -> bytes:
    """An NWM answer without its `reach` block: the reach's name, place and route, whose list of series comes back
    in a different order on each request, so an unchanged forecast would look new every hour."""
    d = json.loads(body)
    d.pop("reach", None)
    return json.dumps(d, separators=(",", ":")).encode()


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
        if product.startswith("nwm_"):
            body = forecast_only(body)
        saved += save(out, lid, product, body, now) is not None
    print(f"{now:%Y-%m-%dT%H:%MZ} saved {saved} new, {failed} failed, of {len(sources())}")
    return 1 if failed > len(sources()) // 2 else 0  # fail loudly only when the source is broadly down


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
