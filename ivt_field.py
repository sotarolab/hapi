"""Fetch the GFS forecast of integrated vapor transport (IVT) as a field over the northeast Pacific, where the
atmospheric rivers that reach California form, and save one file per forecast cycle. site.py turns the saved
cycles into the file the page's map draws.

The source is NOAA's GRIB filter for GFS at 1 degree: eastward wind, northward wind and specific humidity on
the pressure levels weather.py uses, for a box. The filter answers with GRIB2 messages in simple packing (data
template 5.0), which this script decodes itself, so it needs nothing beyond the standard library. IVT is the
integral weather.py computes at a point, here at every grid cell.

shortcut: levels under the ground over high terrain are integrated as the model gives them; mask them with
the surface pressure if the field over land is ever used for more than a picture.

Run: python ivt_field.py [out_dir]   (default: data/)
     writes out/ivt_gfs/<YYYYMMDDHH>.gz, one per cycle; a cycle already saved is not fetched again
"""

from __future__ import annotations

import gzip
import http.client
import json
import struct
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from weather import LEVELS, transport

SOUTH, NORTH, WEST, EAST = 20, 55, 190, 250  # degrees; longitudes east of Greenwich: 170 W to 110 W
HOURS = list(range(0, 121, 6))  # forecast hours of a cycle
PAST = 8  # cycles before the newest whose hour 0 is kept: the two days before
FILTER = (
    "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl?dir=%2Fgfs.{cycle:%Y%m%d}%2F{cycle:%H}%2Fatmos"
    "&file=gfs.t{cycle:%H}z.pgrb2.1p00.f{hour:03d}&var_UGRD=on&var_VGRD=on&var_SPFH=on&{levels}"
    "&subregion=&toplat={north}&leftlon={west}&rightlon={east}&bottomlat={south}"
)
NAMES = {(2, 2): "u", (2, 3): "v", (1, 0): "q"}  # GRIB2 parameter category and number, meteorological products


def signed(raw: int, bits: int) -> int:
    """GRIB writes a negative number as its size with the top bit set."""
    top = 1 << (bits - 1)
    return -(raw & (top - 1)) if raw & top else raw


def messages(body: bytes) -> list[dict]:
    """The GRIB2 messages of an answer as {name, level (hPa), nx, ny, values}, the values in rows from north to
    south, west to east. A message that is not on a latitude-longitude grid in simple packing with no bitmap
    is refused: this decoder reads that one form."""
    out, pos = [], 0
    while body[pos : pos + 4] == b"GRIB":
        end, p, m, pack = pos + struct.unpack(">Q", body[pos + 8 : pos + 16])[0], pos + 16, {}, (0.0, 0, 0, 0)
        while body[p : p + 4] != b"7777":
            n, section = struct.unpack(">IB", body[p : p + 5])
            s = body[p : p + n]
            if section == 3:
                if struct.unpack(">H", s[12:14])[0] != 0:
                    raise ValueError("the grid is not latitude-longitude")
                m["nx"], m["ny"] = struct.unpack(">II", s[30:38])
                m["south_first"] = bool(s[71] & 0x40)
            elif section == 4:
                m["name"] = NAMES.get((s[9], s[10]))
                m["level"] = round(struct.unpack(">I", s[24:28])[0] / 10 ** s[23] / 100)  # Pa in the file
            elif section == 5:
                if struct.unpack(">H", s[9:11])[0] != 0:
                    raise ValueError(f"data template 5.{struct.unpack('>H', s[9:11])[0]}, not simple packing")
                e, d = (signed(x, 16) for x in struct.unpack(">HH", s[15:19]))
                pack = (struct.unpack(">f", s[11:15])[0], e, d, s[19])
            elif section == 6 and s[5] != 255:
                raise ValueError("the message has a bitmap")
            elif section == 7:
                (ref, e, d, bits), cells, data = pack, m["nx"] * m["ny"], s[5:]
                whole, last = int.from_bytes(data, "big"), len(data) * 8
                raw = (
                    [(whole >> (last - (i + 1) * bits)) & ((1 << bits) - 1) for i in range(cells)]
                    if bits
                    else [0] * cells
                )
                values = [(ref + x * 2.0**e) / 10.0**d for x in raw]
                rows = [values[r * m["nx"] : (r + 1) * m["nx"]] for r in range(m["ny"])]
                m["values"] = [x for row in (reversed(rows) if m.pop("south_first") else rows) for x in row]
            p += n
        out.append(m)
        pos = end
    return out


def field(body: bytes) -> tuple[list[int], list[int]]:
    """Eastward and northward IVT in whole kg/m/s at every cell, north to south, from one forecast hour's answer."""
    got = {(m["name"], m["level"]): m["values"] for m in messages(body)}
    missing = [(name, p) for name in "uvq" for p in LEVELS if (name, p) not in got]
    if missing:
        raise ValueError(f"the answer lacks {missing[:3]}")
    u, v = [], []
    for i in range(len(got[("q", LEVELS[0])])):
        qu, qv = transport(
            [(p * 100, got[("q", p)][i] * got[("u", p)][i], got[("q", p)][i] * got[("v", p)][i]) for p in LEVELS]
        )
        u.append(round(qu))
        v.append(round(qv))
    return u, v


def get(url: str) -> bytes | None:
    """The answer, or None. A cycle NOAA has not posted yet answers 404 on every run until it has, so this says nothing."""
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "hapi-archiver"}), timeout=60
        ) as r:
            return r.read()
    except (OSError, http.client.HTTPException):
        return None


def url(cycle: datetime, hour: int) -> str:
    levels = "&".join(f"lev_{p}_mb=on" for p in LEVELS)
    return FILTER.format(cycle=cycle, hour=hour, levels=levels, north=NORTH, south=SOUTH, west=WEST, east=EAST)


def path(out: Path, cycle: datetime) -> Path:
    return out / "ivt_gfs" / f"{cycle:%Y%m%d%H}.gz"


def load(p: Path) -> dict:
    return json.loads(gzip.decompress(p.read_bytes()))


def fetch_cycle(out: Path, cycle: datetime, hours: list[int], get=get) -> bool:
    """Fetch the hours of a cycle and save them as one file. False, and nothing saved, if any hour is missing."""
    frames = []
    for hour in hours:
        body = get(url(cycle, hour))
        if body is None or body[:4] != b"GRIB":
            print(f"BAD PAYLOAD gfs {cycle:%Y%m%d%H} f{hour:03d}", file=sys.stderr)
            return False
        frames.append(field(body))
    saved = {
        "cycle": f"{cycle:%Y-%m-%dT%H:00Z}",
        "hours": hours,
        "north": NORTH,
        "south": SOUTH,
        "west": WEST - 360,
        "east": EAST - 360,
        "nx": EAST - WEST + 1,
        "ny": NORTH - SOUTH + 1,
        "u": [u for u, _ in frames],
        "v": [v for _, v in frames],
    }
    path(out, cycle).parent.mkdir(parents=True, exist_ok=True)
    path(out, cycle).write_bytes(gzip.compress(json.dumps(saved, separators=(",", ":")).encode(), mtime=0))
    return True


def newest_cycle(out: Path, now: datetime, get=get) -> datetime | None:
    """The newest cycle NOAA has posted in full and that is not saved yet. None when the newest one is saved."""
    first = now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)
    for back in range(4):
        cycle = first - timedelta(hours=6 * back)
        if path(out, cycle).exists() and load(path(out, cycle))["hours"] == HOURS:
            return None
        if (get(url(cycle, HOURS[-1])) or b"")[:4] == b"GRIB":  # its last hour is up, so the others are
            return cycle
    return None


def main(out: Path, now: datetime | None = None, get=get) -> int:
    now = now or datetime.now(UTC)
    cycle = newest_cycle(out, now, get)
    failed = int(cycle is not None and not fetch_cycle(out, cycle, HOURS, get))
    saved = sorted((out / "ivt_gfs").glob("*.gz"))
    past = 0
    if saved:  # the analyses of the two days before the newest cycle, fetched once
        newest = datetime.strptime(saved[-1].stem, "%Y%m%d%H").replace(tzinfo=UTC)
        for back in range(1, PAST + 1):
            if not path(out, newest - timedelta(hours=6 * back)).exists():
                past += fetch_cycle(out, newest - timedelta(hours=6 * back), [0], get)
    print(
        f"{now:%Y-%m-%dT%H:%MZ} ivt field: {f'saved cycle {cycle:%Y%m%d%H}' if cycle and not failed else 'no new cycle'}, {past} past analyses"
    )
    return failed


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
