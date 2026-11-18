import gzip
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from test_score import (
    test_score_one_forecast_day as make_fixture,  # builds obs, a HEFS file and a model forecast in tmp_path
)

spec = importlib.util.spec_from_file_location("site_builder", Path(__file__).parent.parent / "site.py")
assert spec is not None and spec.loader is not None
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def test_build_writes_index_and_point_files(tmp_path):
    make_fixture(tmp_path)
    idx = site.build(tmp_path, datetime(2026, 11, 15, tzinfo=UTC))
    assert idx["record_start"] == "20261114" and idx["archive_days"] == 1
    assert {p["kind"] for p in idx["points"]} == {"reservoir", "gauge"} and len(idx["points"]) == 15 + 12
    fol = json.loads((tmp_path / "site" / "points" / "FOLC1.json").read_text())
    # issued 2026-11-14: the fan starts on the issue day, and its second day is lead 1, the row stamped 2026-11-16
    assert fol["hefs"]["dates"] == ["2026-11-14", "2026-11-15"] and fol["hefs"]["p50"] == [700, 1000]
    assert fol["models"]["embalse_v1"]["q50"] == [1000, 600] and fol["obs"][-1] == ["2026-11-15", 1000.0]
    assert site.percentiles([3, 1, 2]) == [1, 1, 2, 3, 3]
    guec = json.loads((tmp_path / "site" / "points" / "GUEC1.json").read_text())
    assert guec["hefs"] is None and guec["official"] is None and guec["live"] is None and guec["alerts"] == []
    assert fol["live"] is None and fol["alerts"] == []
    (tmp_path / "live").mkdir()
    (tmp_path / "live" / "GUEC1.json").write_text(
        json.dumps(
            {
                "source": "NWS observed at GUEC1",
                "times": ["2026-11-15T00:00:00Z"],
                "cfs": [204],
                "stage_ft": [4.5],
                "alerts": [{"label": "Action", "ft": 29, "cfs": 37700}],
            }
        )
    )
    site.build(tmp_path, datetime(2026, 11, 15, tzinfo=UTC))
    guec = json.loads((tmp_path / "site" / "points" / "GUEC1.json").read_text())
    assert guec["live"]["cfs"] == [204] and "alerts" not in guec["live"] and guec["alerts"][0]["cfs"] == 37700
    assert fol["weather"] is None and guec["weather"] is None  # nothing archived by weather.py


def test_weather_panel_is_built_from_the_issue_hour(tmp_path):
    hours = [f"2026-11-{16 + h // 24:02d}T{h % 24:02d}:00" for h in range(96)]
    ivt = [100] * 12 + [600] * 30 + [100] * 54  # 30 h at tier 2: CAT 2, starting at hour 12
    w = {
        "times": hours,
        "ivt": ivt,
        "precip_mm": {"GFS": [2.54] * 96, "ICON": [5.08] * 90 + [None] * 6},
        "freezing_m": {"GFS": [2000.0] * 48 + [3000.0] * 48},
    }
    d = tmp_path / "weather" / "FOLC1"
    d.mkdir(parents=True)
    (d / "20261116T063700Z.gz").write_bytes(gzip.compress(json.dumps(w).encode()))
    panel = site.weather_latest(tmp_path, "FOLC1")
    assert panel["times"][0] == "2026-11-16T00:00" and len(panel["times"]) == 96  # the charts keep every archived hour
    ar, precip, freezing = panel["tiles"]
    assert ar["value"] == "CAT 2: Moderate" and ar["flag"] == "warn"
    assert "peak 600 kg/m/s · arrives Nov 16 12Z · 30 h above 250" in ar["note"]
    assert precip == {
        "label": "Precip through Nov 19, GFS",
        "value": "9.00 in",
        "note": "",
        "flag": None,
    }  # ICON stops short
    assert freezing["value"] == "6,560 to 9,840 ft"
    charts = {c["id"]: c for c in panel["charts"]}
    assert (
        list(charts) == ["precip", "ivt", "freezing"]
        and charts["ivt"]["line"]["value"] == 250
        and "fetched 2026-11-16 06:37Z" in panel["note"]
    )
    assert charts["precip"]["series"][0]["values"][-1] == 9.0 and charts["precip"]["series"][1]["values"][-1] is None
    assert charts["precip"]["series"][0]["values"][:7] == [None] * 6 + [
        0.1
    ]  # the running total starts at the issue hour
    assert charts["precip"]["bars"]["label"] == "GFS, hourly"
    (d / "20261125T003700Z.gz").write_bytes(gzip.compress(json.dumps(w).encode()))
    assert site.weather_latest(tmp_path, "FOLC1") is None  # a file fetched after its last forecast hour shows nothing


def test_weather_stitches_the_newest_value_per_hour(tmp_path):
    day = lambda d: [f"2026-11-{d + h // 24:02d}T{h % 24:02d}:00" for h in range(48)]
    old = {
        "times": day(16),
        "ivt": [100] * 48,
        "precip_mm": {"GFS": [25.4] * 48},
    }  # a file from before the new variables
    new = {
        "times": day(17),
        "ivt": [200] * 48,
        "precip_mm": {"GFS": [50.8] * 48},
        "temperature_c": {"GFS": [0.0] * 48},
        "snow_depth_m": {"GFS": [0.0254] * 48},
        "snowfall_cm": {"GFS": [2.54] * 48},
        "soil_m3m3": {"GFS 0-10 cm": [0.25] * 48},
        "gust_kmh": {"GFS": [16.0934] * 48},
    }
    d = tmp_path / "weather" / "FOLC1"
    d.mkdir(parents=True)
    (d / "20261116T003700Z.gz").write_bytes(gzip.compress(json.dumps(old).encode()))
    (d / "20261117T003700Z.gz").write_bytes(gzip.compress(json.dumps(new).encode()))
    panel = site.weather_latest(tmp_path, "FOLC1")
    charts = {c["id"]: c for c in panel["charts"]}
    assert len(panel["times"]) == 72 and list(charts) == ["precip", "ivt", "temperature", "snow", "soil", "gusts"]
    ivt = charts["ivt"]["series"][0]["values"]
    assert ivt[0] == 100 and ivt[24] == 200  # Nov 16 from the older file, Nov 17 on from the newer
    assert (
        charts["precip"]["bars"]["values"][23:25] == [1.0, 2.0] and charts["precip"]["series"][0]["values"][24] == 2.0
    )
    assert (
        charts["temperature"]["series"][0]["values"][23:25] == [None, 32.0]
        and charts["temperature"]["line"]["value"] == 32
    )
    assert charts["snow"]["series"][0] == {
        "label": "GFS, depth",
        "colour": "--cool",
        "values": [None] * 24 + [1.0] * 48,
    }
    assert charts["snow"]["bars"]["values"][24] == 1.0 and charts["soil"]["series"][0]["values"][24] == 25.0
    assert charts["gusts"]["series"][0]["values"][24] == 10 and charts["soil"]["series"][0]["label"] == "GFS 0-10 cm"


def test_gauge_page_carries_the_newest_hourly_model_forecast(tmp_path):
    d = tmp_path / "forecasts" / "quantile_flow_hourly_v1_s0" / "GUEC1"
    d.mkdir(parents=True)
    rows = "2026-11-18T07:00Z,1,900,950,1000,1050,1100\n2026-11-18T08:00Z,2,950,1000,1050,1150,1200\n"
    (d / "2026-11-18T06Z.csv").write_text("time,lead,q05,q25,q50,q75,q95\n" + rows)
    (d / "2026-11-18T00Z.csv").write_text(
        "time,lead,q05,q25,q50,q75,q95\n" + rows.replace("T07", "T01").replace("T08", "T02")
    )
    (d / "2026-11-18T12Z.csv").write_text("time,lead,q50\n2026-11-18T19:00Z,1,1\n")  # breaks the contract: passed over
    site.build(tmp_path, datetime(2026, 11, 18, 7, tzinfo=UTC))
    model = json.loads((tmp_path / "site" / "points" / "GUEC1.json").read_text())["models"][
        "quantile_flow_hourly_v1_s0"
    ]
    assert model["issued"] == "2026-11-18T06Z" and model["dates"] == ["2026-11-18T07:00Z", "2026-11-18T08:00Z"]
    assert model["q50"] == [1000, 1050] and model["first"] == "next hour"
