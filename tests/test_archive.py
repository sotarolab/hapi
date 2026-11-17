import gzip
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import archive


def test_save_skips_unchanged_and_keeps_changed(tmp_path):
    t1 = datetime(2026, 11, 14, 12, tzinfo=UTC)
    t2 = datetime(2026, 11, 14, 18, tzinfo=UTC)
    p1 = archive.save(tmp_path, "GUEC1", "hefs_daily", b"GMT,a", t1)
    assert p1 is not None and gzip.decompress(p1.read_bytes()) == b"GMT,a"
    assert archive.save(tmp_path, "GUEC1", "hefs_daily", b"GMT,a", t2) is None
    p2 = archive.save(tmp_path, "GUEC1", "hefs_daily", b"GMT,b", t2)
    assert p2 is not None and p2.name == "20261114T180000Z.gz" and len(list(p1.parent.iterdir())) == 2


def test_sources_cover_every_point_once_per_product():
    s = archive.sources()
    assert len(s) == len(set(s)) == len(archive.INFLOW) + 3 * len(archive.FLOOD)
