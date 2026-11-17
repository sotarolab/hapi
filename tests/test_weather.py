import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import UTC

import weather


def test_ivt_matches_the_analytic_integral():
    # Saturated air at 0 C under a 10 m/s westerly at every level: q is known per level, the wind is constant.
    q = lambda p: 0.622 * 6.112 / (p - 0.378 * 6.112)
    levels = [1000, 900, 800]
    expected = sum((q(a) + q(b)) / 2 * 10 * (a - b) * 100 for a, b in zip(levels, levels[1:])) / 9.81
    got = weather.ivt([(p, 10.0, 270, 100, 0.0) for p in levels])
    assert got is not None and abs(got - expected) < 1e-9 and 70 < got < 90
    assert weather.ivt([(1000, 10.0, 270, 100, 0.0), (900, None, 270, 100, 0.0)]) is None


def test_ivt_adds_the_two_wind_components():
    south = weather.ivt([(p, 10.0, 180, 100, 0.0) for p in (1000, 900)])
    west = weather.ivt([(p, 10.0, 270, 100, 0.0) for p in (1000, 900)])
    southwest = weather.ivt([(p, 10.0, 225, 100, 0.0) for p in (1000, 900)])
    assert south is not None and west is not None and southwest is not None
    assert abs(south - west) < 1e-9 and abs(southwest - west) < 1e-9  # magnitude does not depend on direction


def test_derive_keeps_models_with_values_and_computes_ivt():
    times = ["2026-11-16T00:00", "2026-11-16T01:00"]
    surface = {
        "hourly": {
            "time": times,
            **{f"precipitation_{m}": [0.1, 0.2] for m in weather.MODELS},
            "freezing_level_height_gfs_seamless": [2500.0, 2400.0],
            "freezing_level_height_ecmwf_ifs025": [None, None],
        }
    }
    column = {
        "wind_speed": [10.0, 20.0],
        "wind_direction": [270, 270],
        "relative_humidity": [100, 100],
        "temperature": [0.0, 0.0],
    }
    profile = {
        "hourly": {"time": times, **{f"{v}_{p}hPa": column[v] for p in weather.LEVELS for v in weather.LEVEL_VARS}}
    }
    d = weather.derive(surface, profile)
    assert d["times"] == times and list(d["precip_mm"]) == ["GFS", "ECMWF", "ICON", "NBM"]
    assert d["freezing_m"] == {"GFS": [2500.0, 2400.0]}  # ECMWF has no freezing level and is left out
    assert d["ivt"][0] > 0 and abs(d["ivt"][1] - 2 * d["ivt"][0]) <= 1  # twice the wind, twice the IVT (rounded)


def test_urls_name_every_level_and_model():
    assert weather.PROFILE.count("hPa") == len(weather.LEVELS) * len(weather.LEVEL_VARS)
    assert all(m in weather.SURFACE for m in weather.MODELS) and "{lat}" in weather.SURFACE


def test_fresh_within_five_hours_of_the_newest_file(tmp_path):
    from datetime import datetime

    d = tmp_path / "weather" / "FOLC1"
    d.mkdir(parents=True)
    (d / "20261116T043700Z.gz").write_bytes(b"")
    assert weather.fresh(tmp_path, "FOLC1", datetime(2026, 11, 16, 9, 0, tzinfo=UTC))
    assert not weather.fresh(tmp_path, "FOLC1", datetime(2026, 11, 16, 9, 40, tzinfo=UTC))
    assert not weather.fresh(tmp_path, "GUEC1", datetime(2026, 11, 16, 9, 0, tzinfo=UTC))
