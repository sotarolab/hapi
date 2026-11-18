import gzip
import json
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import ivt_field
import weather

REAL = Path(__file__).parent / "fixtures" / "gfs_ugrd_850mb_f006.grb"  # NOAA's answer for one field, 2026-11-17 12Z


def test_messages_decode_a_real_gfs_field():
    (m,) = ivt_field.messages(REAL.read_bytes())
    assert (m["name"], m["level"], m["nx"], m["ny"]) == ("u", 850, 61, 36) and len(m["values"]) == 61 * 36
    assert -40 < min(m["values"]) < 0 < max(m["values"]) < 40  # an eastward wind in m/s
    assert "south_first" not in m  # the rows are turned to run north to south


def test_a_message_with_another_packing_is_refused():
    body = bytearray(REAL.read_bytes())
    p = 16
    while body[p + 4] != 5:  # walk the sections to the data representation
        p += struct.unpack(">I", body[p : p + 4])[0]
    body[p + 9 : p + 11] = struct.pack(">H", 3)  # complex packing with spatial differencing
    try:
        ivt_field.messages(bytes(body))
    except ValueError as e:
        assert "not simple packing" in str(e)
    else:
        raise AssertionError("a message in complex packing was decoded")


def test_ivt_of_a_uniform_column_matches_the_hand_computed_value():
    # q = 0.01 kg/kg and an eastward wind of 10 m/s from 1000 to 300 hPa: 0.01 * 10 * 70,000 Pa / 9.81 = 713.6 kg/m/s
    east, north = weather.transport([(p * 100, 0.01 * 10, 0.0) for p in weather.LEVELS])
    assert abs(east - 713.56) < 0.01 and north == 0


def test_weather_ivt_is_the_magnitude_of_the_components():
    column = lambda direction, speed: [(p, speed, direction, 80, 10 - (1000 - p) / 20) for p in weather.LEVELS]
    west, south, double = weather.ivt(column(270, 20)), weather.ivt(column(180, 20)), weather.ivt(column(270, 40))
    assert west is not None and south is not None and double is not None
    assert abs(west - south) < 1e-9  # the same from any direction
    assert abs(double - 2 * west) < 1e-9  # and twice the wind is twice the transport


def run(tmp_path, now, posted, calls):
    """Run the script with NOAA replaced: `posted` are the cycle hours (as in the file names) that answer."""

    def get(url):
        calls.append(url)
        return b"GRIB" if any(f"gfs.t{hh}z" in url and f"gfs.{day}" in url for day, hh in posted) else None

    return ivt_field.main(tmp_path, now, get)


def test_a_saved_cycle_is_not_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr(ivt_field, "field", lambda body: ([1, 2], [3, 4]))
    days = [("20261118", "00"), ("20261117", "18"), ("20261117", "12"), ("20261117", "06"), ("20261117", "00")]
    posted = days + [("20261116", hh) for hh in ("18", "12", "06", "00")]
    calls = []
    assert run(tmp_path, datetime(2026, 11, 18, 5, tzinfo=UTC), posted, calls) == 0
    assert len(calls) == 1 + len(ivt_field.HOURS) + ivt_field.PAST  # the check, the cycle, the analyses before it
    saved = json.loads(gzip.decompress((tmp_path / "ivt_gfs" / "2026111800.gz").read_bytes()))
    assert (
        saved["hours"] == ivt_field.HOURS and saved["u"][0] == [1, 2] and (saved["west"], saved["east"]) == (-170, -110)
    )
    assert json.loads(gzip.decompress((tmp_path / "ivt_gfs" / "2026111618.gz").read_bytes()))["hours"] == [0]
    run(tmp_path, datetime(2026, 11, 18, 5, tzinfo=UTC), posted, calls)
    assert len(calls) == 1 + len(ivt_field.HOURS) + ivt_field.PAST  # nothing asked: the newest cycle is saved
    run(tmp_path, datetime(2026, 11, 18, 7, tzinfo=UTC), posted, calls)
    assert len(calls) == 2 + len(ivt_field.HOURS) + ivt_field.PAST  # one check for the 06Z cycle, not posted yet


def test_a_cycle_with_a_missing_hour_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(ivt_field, "field", lambda body: ([1], [1]))
    answers = iter([b"GRIB", b"GRIB", b"<html>not yet</html>"])
    assert not ivt_field.fetch_cycle(
        tmp_path, datetime(2026, 11, 18, tzinfo=UTC), [0, 6, 12], lambda url: next(answers)
    )
    assert not (tmp_path / "ivt_gfs").exists()
