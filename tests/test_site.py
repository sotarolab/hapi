import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from test_score import test_score_one_forecast_day as make_fixture  # builds obs, a HEFS file and a model forecast in tmp_path

spec = importlib.util.spec_from_file_location("site_builder", Path(__file__).parent.parent / "site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def test_build_writes_index_and_point_files(tmp_path):
    make_fixture(tmp_path)
    idx = site.build(tmp_path, datetime(2026, 11, 15, tzinfo=timezone.utc))
    assert idx["record_start"] == "20261114" and idx["archive_days"] == 1
    assert {p["kind"] for p in idx["points"]} == {"reservoir", "gauge"} and len(idx["points"]) == 15 + 12
    fol = json.loads((tmp_path / "site" / "points" / "FOLC1.json").read_text())
    assert fol["hefs"]["dates"][:2] == ["2026-11-14", "2026-11-15"] and fol["hefs"]["p50"][1] == 1000
    assert fol["models"]["embalse_v1"]["q50"] == [1000, 600] and fol["obs"][-1] == ["2026-11-15", 1000.0]
    assert site.percentiles([3, 1, 2]) == [1, 1, 2, 3, 3]
    guec = json.loads((tmp_path / "site" / "points" / "GUEC1.json").read_text())
    assert guec["hefs"] is None and guec["official"] is None and guec["flood_stages_ft"] == [32, 35, 40]
