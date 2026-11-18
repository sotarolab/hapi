import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import live

RATING = [(4.0, 100), (29, 37700), (32, 45000), (35, 53400), (40, 68000), (50, 101000)]


def test_cdec_hourly_is_pst_and_keeps_missing_hours():
    body = (
        b"STATION_ID,DURATION,SENSOR_NUMBER,SENSOR_TYPE,DATE TIME,OBS DATE,VALUE,DATA_FLAG,UNITS\n"
        b"FOL,H,76,INFLOW,20261116 2300,20261116 2300,358, ,CFS\n"
        b"FOL,H,76,INFLOW,20261117 0000,20261117 0000,---, ,CFS\n"
        b"FOL,H,76,INFLOW,20261117 0100,20261117 0100,-12, ,CFS\n"
    )
    assert live.cdec_hourly(body) == (
        ["2026-11-17T07:00Z", "2026-11-17T08:00Z", "2026-11-17T09:00Z"],
        [358.0, None, -12.0],
    )


def test_centred_mean_needs_a_full_window():
    assert live.centred_mean([0, 4, 2, 6, 8, 12], 4) == [None, None, 3, 5, 7, None]  # stamped two hours into its four
    assert live.centred_mean([0, 4, None, None, 8, 10], 4) == [None] * 6  # never three of four valid
    assert live.centred_mean([0, 4, None, 6, 8, 10], 4)[2:5] == [3, 6, 8]


def test_informative_compares_spread_with_the_mean():
    assert live.informative([1000.0, 1200.0] * 24)
    assert not live.informative([1000.0, -900.0, None] * 24)  # swings around a small mean
    assert not live.informative([1000.0, 1200.0] * 12)  # a single day is too short to judge


def test_nwps_observed_scales_kcfs():
    d = {
        "secondaryUnits": "kcfs",
        "data": [
            {"validTime": "2026-11-16T21:00:00Z", "primary": 4.51, "secondary": 0.204},
            {"validTime": "2026-11-16T22:00:00Z", "primary": -999, "secondary": -999},
        ],
    }
    assert live.nwps_observed(d) == {
        "times": ["2026-11-16T21:00:00Z", "2026-11-16T22:00:00Z"],
        "stage_ft": [4.51, None],
        "cfs": [204, None],
    }


def test_alerts_use_nwps_flow_or_the_rating_curve():
    gauge = {
        "flood": {
            "categories": {
                "major": {"stage": 40, "flow": -9999},
                "moderate": {"stage": 35, "flow": 50000},
                "minor": {"stage": 33.5, "flow": -9999},
                "action": {"stage": -9999, "flow": -9999},
            }
        }
    }
    assert live.alerts(gauge, RATING) == [
        {"label": "Minor", "ft": 33.5, "cfs": 49200},
        {"label": "Moderate", "ft": 35, "cfs": 53400},
        {"label": "Major", "ft": 40, "cfs": 68000},
    ]
    assert live.rating_flow(RATING, 60) is None and live.alerts({"flood": None}, RATING) == []
    full = {"flood": {"categories": {"minor": {"stage": 32, "flow": 45000}, "action": {"stage": 29, "flow": 37700}}}}
    assert [a["cfs"] for a in live.alerts(full, [])] == [37700, 45000]  # every flow given: NWPS's own numbers


def test_gauge_record_appends_and_never_shrinks(tmp_path):
    seen = lambda hour: datetime(2026, 11, 30, hour, 41, tzinfo=UTC)
    obs = {"times": ["2026-11-30T21:00:00Z", "2026-11-30T22:00:00Z"], "cfs": [204, 210], "stage_ft": [4.51, 4.6]}
    assert live.record(tmp_path, "GUEC1", obs, seen(22)) == 2
    # an hour later the feed has dropped 21:00, revised 22:00, and serves two new times, one on the next day
    obs = {
        "times": ["2026-11-30T22:00:00Z", "2026-11-30T23:00:00Z", "2026-12-01T00:00:00Z"],
        "cfs": [215, 230, None],
        "stage_ft": [4.6, 4.8, 5.0],
    }
    assert live.record(tmp_path, "GUEC1", obs, seen(23)) == 3
    assert live.record(tmp_path, "GUEC1", obs, seen(23)) == 0  # the same fetch again adds nothing
    d = tmp_path / "gauge_obs" / "GUEC1"
    assert (d / "2026-11-30.csv").read_text().splitlines() == [
        "time,cfs,stage_ft,seen",
        "2026-11-30T21:00:00Z,204,4.51,2026-11-30T22:41Z",  # no longer served, still here
        "2026-11-30T22:00:00Z,210,4.6,2026-11-30T22:41Z",  # the first value published
        "2026-11-30T22:00:00Z,215,4.6,2026-11-30T23:41Z",  # and its revision
        "2026-11-30T23:00:00Z,230,4.8,2026-11-30T23:41Z",
    ]
    assert (d / "2026-12-01.csv").read_text().splitlines() == [
        "time,cfs,stage_ft,seen",
        "2026-12-01T00:00:00Z,,5,2026-11-30T23:41Z",
    ]


def test_since_keeps_the_window():
    d = {"source": "x", "times": ["2026-11-09T00:00Z", "2026-11-10T00:00Z"], "cfs": [1, 2], "stage_ft": None}
    assert live.since(d, "2026-11-09T12:00Z") == {
        "source": "x",
        "times": ["2026-11-10T00:00Z"],
        "cfs": [2],
        "stage_ft": None,
    }
