"""Fetch past HEFS issues from CNRFC's dated archive into a hindcast folder that has the data folder's
layout, so score.py scores them unchanged. CNRFC keeps every 12Z issue since January 2014 as one zip per
river group. Only the start of each zip is read: the issue day and the 14 leads score.py scores.

A hindcast is not the live record. It is kept in its own folder, never pooled with the data folder and
never sent to the data branch.

Run: python retro.py out_dir first_day last_day     (python retro.py hindcast 2015-10-01 2025-09-30)
then: python score.py out_dir
"""

from __future__ import annotations

import gzip
import http.client
import struct
import sys
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import BinaryIO

from score import LEADS

ARCHIVE = "https://www.cnrfc.noaa.gov/csv/{day:%Y%m%d}12_{group}_hefs_csv_daily.zip"
# River group -> the reservoir points it holds. Checked on eight dates from 2014-01-01 to 2025-10-01.
GROUPS = {
    "RussianNapa": ["LAMC1", "WSDC1"],
    "FeatherYuba": ["ORDC1", "NBBC1"],
    "UpperSacramento": ["SHDC1"],
    "american": ["FOLC1"],
    "SanJoaquin": ["NDPC1", "NMSC1", "FRAC1", "EXQC1"],
    "Tulare": ["ISAC1", "TMDC1", "SCSC1"],
}
ROWS = 2 + 1 + max(LEADS)  # two header rows, the issue day, the leads


def head(stream: BinaryIO, lines: int) -> list[str] | None:
    """The first lines of the file inside a zip, reading the stream from its start and no further than needed."""
    h = stream.read(30)  # zip local file header
    if h[:4] != b"PK\x03\x04" or h[8:10] != b"\x08\x00":  # CNRFC answers a missing file with an HTML page
        return None
    name, extra = struct.unpack("<HH", h[26:30])
    stream.read(name + extra)
    inflate, text = zlib.decompressobj(-15), b""
    while text.count(b"\n") < lines and (chunk := stream.read(32768)):
        text += inflate.decompress(chunk)
    return text.decode().splitlines()[:lines]


def split(rows: list[str], lids: list[str]) -> dict[str, bytes]:
    """{lid: that point's columns as a file in the layout archive.py saves}. CNRFC names a point with or
    without a trailing F inside the group files (ORDC1 in 2014, ORDC1F since 2015)."""
    cells = [r.split(",") for r in rows]
    out = {}
    for lid in lids:
        cols = [i for i, c in enumerate(cells[0]) if c in (lid, lid + "F")]
        if cols:
            out[lid] = "\n".join(",".join([r[0], *(r[i] for i in cols)]) for r in cells).encode() + b"\n"
    return out


def path(out: Path, lid: str, day: date) -> Path:
    return out / "hefs_daily" / lid / f"{day:%Y%m%d}T120000Z.gz"  # archive.py's file name, at the issue hour


def issue(day: date, group: str) -> list[str] | None:
    req = urllib.request.Request(ARCHIVE.format(day=day, group=group), headers={"User-Agent": "hapi-archiver"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return head(r, ROWS)
    except (OSError, http.client.HTTPException, zlib.error) as e:
        print(f"FAILED {group} {day}: {e}", file=sys.stderr)
        return None


def main(out: Path, first: date, last: date, fetch=issue) -> int:
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    jobs = [(d, g) for d in days for g, lids in GROUPS.items() if not all(path(out, x, d).exists() for x in lids)]
    saved = bad = 0
    with ThreadPoolExecutor(4) as pool:  # four short reads at a time
        for (day, group), rows in zip(jobs, pool.map(lambda j: fetch(*j), jobs)):
            if rows is None or len(rows) < ROWS or not rows[0].startswith("GMT") or rows[2][:10] != f"{day}":
                bad += 1
                print(f"BAD PAYLOAD {group} {day}", file=sys.stderr)
                continue
            found = split(rows, GROUPS[group])
            for lid in set(GROUPS[group]) - set(found):
                print(f"MISSING {lid} {day}", file=sys.stderr)
            for lid, body in found.items():
                p = path(out, lid, day)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(gzip.compress(body, mtime=0))
                saved += 1
    print(f"{first} to {last}: saved {saved} files, {bad} bad of {len(jobs)} group files asked")
    return 1 if bad > len(jobs) // 2 else 0  # fail loudly only when the source is broadly down


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])))
