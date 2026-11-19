import gzip
import json
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
    assert len(s) == len(set(s)) == len(archive.INFLOW) + 5 * len(archive.FLOOD)


def test_every_flood_gauge_has_its_nwm_reach_and_a_real_answer_is_a_json_payload():
    assert set(archive.NWM_REACH) == set(archive.FLOOD)
    nwm = [(lid, url) for lid, product, url in archive.sources() if product.startswith("nwm_")]
    assert len(nwm) == 2 * len(archive.FLOOD) and all("series=" in url for _, url in nwm)
    body = (Path(__file__).parent / "fixtures" / "nwm_short_range_8273703.json").read_bytes()  # NWPS, 2026-11-19
    assert body[:1] == b"{" and b'"shortRange"' in body  # the check main() applies to every JSON product


def test_an_nwm_answer_is_saved_without_its_reach_block():
    body = (Path(__file__).parent / "fixtures" / "nwm_short_range_8273703.json").read_bytes()
    d = json.loads(body)
    d["reach"]["streamflow"] = list(reversed(d["reach"]["streamflow"]))  # what the API does between two requests
    kept = archive.forecast_only(body)
    assert kept == archive.forecast_only(json.dumps(d).encode())  # so an unchanged forecast saves nothing
    assert "reach" not in json.loads(kept) and json.loads(kept)["shortRange"] == json.loads(body)["shortRange"]
