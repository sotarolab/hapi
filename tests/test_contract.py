import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import contract

REAL = Path(__file__).parent / "fixtures" / "forecasts" / "quantile_inflow_v1_s0" / "FOLC1" / "2026-11-15.csv"
GOOD = "date,lead,q05,q50,q95\n2026-11-16,1,900,1000,1100\n2026-11-17,2,500,600,700\n"


def write(tmp_path, text, name="2026-11-15.csv"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_real_caudal_file_passes():
    assert REAL.read_text().startswith("date,lead,q05,q25,q50,q75,q90,q95,q99")  # seven quantiles, as issued
    assert contract.check_forecast(REAL) == []


def test_good_file_passes_and_the_name_must_be_a_date(tmp_path):
    assert contract.check_forecast(write(tmp_path, GOOD)) == []
    assert "not an issue date" in contract.check_forecast(write(tmp_path, GOOD, "latest.csv"))[0]
    assert "header" in contract.check_forecast(write(tmp_path, GOOD.replace("q05,q50,q95", "q50,q05,q95")))[0]
    assert "header" in contract.check_forecast(write(tmp_path, GOOD.replace("q05", "low")))[0]


def test_missing_lead_fails(tmp_path):
    errors = contract.check_forecast(write(tmp_path, GOOD.replace("2026-11-17,2", "2026-11-18,3")))
    assert errors == ["row 2 has lead 3: leads run 1, 2, ... with none missing"]


def test_quantile_crossing_fails(tmp_path):
    errors = contract.check_forecast(write(tmp_path, GOOD.replace("900,1000,1100", "1000,900,1100")))
    assert errors == ["row 1: the quantiles decrease"]


def test_date_not_issue_plus_lead_fails(tmp_path):
    errors = contract.check_forecast(write(tmp_path, GOOD, "2026-11-14.csv"))
    assert errors[0] == "row 1: 2026-11-16 is not the issue date 2026-11-14 plus 1 days" and len(errors) == 2


def test_negative_and_unparsable_values_fail(tmp_path):
    assert "negative" in contract.check_forecast(write(tmp_path, GOOD.replace("900", "-1")))[0]
    assert "does not parse" in contract.check_forecast(write(tmp_path, GOOD.replace("900", "n/a")))[0]
    assert contract.check_forecast(write(tmp_path, "date,lead,q50\n")) == ["no forecast rows"]


def test_manifest_requires_keys(tmp_path, capsys):
    p = tmp_path / "MODEL.json"
    assert contract.read_manifest(p) is None  # no manifest is allowed
    full = {k: "x" for k in contract.MANIFEST_KEYS}
    p.write_text(json.dumps(full))
    assert contract.read_manifest(p) == full
    p.write_text(json.dumps({k: v for k, v in full.items() if k != "caudal_commit"}))
    assert contract.read_manifest(p) is None and "missing caudal_commit" in capsys.readouterr().err
