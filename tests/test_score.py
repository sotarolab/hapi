import gzip
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import score


def test_crps_matches_pairwise_formula():
    rng = random.Random(0)
    m = [rng.lognormvariate(7, 1) for _ in range(44)]
    y = 1500.0
    n = len(m)
    pairwise = sum(abs(a - b) for a in m for b in m) / n**2 * n / (n - 1)
    assert abs(score.crps(m, y) - (sum(abs(x - y) for x in m) / n - 0.5 * pairwise)) < 1e-6
    assert score.crps([1200.0], y) == 300.0  # one member: plain absolute error


def test_read_hefs_keys_a_row_by_the_day_before_its_stamp(tmp_path):
    p = tmp_path / "x.gz"
    p.write_bytes(gzip.compress(b"GMT,FOLC1\n,SQME\n2026-11-14 12:00:00,0.5\n2026-11-15 12:00:00,1.5\n"))
    assert score.read_hefs(p) == {date(2026, 11, 13): [500.0], date(2026, 11, 14): [1500.0]}


def test_missing_marker_is_not_a_forecast(tmp_path):
    d = tmp_path / "hefs_daily" / "FOLC1"
    d.mkdir(parents=True)
    body = b"GMT,FOLC1,FOLC1\n,SQME,SQME\n2026-11-14 12:00:00,0.5,0.5\n2026-11-15 12:00:00,-999,1.5\n"
    (d / "20261114T123000Z.gz").write_bytes(gzip.compress(body + b"2026-11-16 12:00:00,-999,-999\n"))
    fc = score.read_hefs(d / "20261114T123000Z.gz")
    assert fc == {date(2026, 11, 13): [500.0, 500.0], date(2026, 11, 14): [1500.0]}  # the marker and its day are gone
    (d / "20261115T123000Z.gz").write_bytes(gzip.compress(b"GMT,FOLC1\n,SQME\n2026-11-15 12:00:00,-999\n"))
    issues = [issue for _, issue, _ in score.forecasts(tmp_path, "FOLC1")]
    assert issues == [date(2026, 11, 14)]  # the file with no analysis is left out whole


def test_score_one_forecast_day(tmp_path):
    obs = [(f"{yr}-11-15", 800 + yr % 7 * 10) for yr in range(2000, 2026)]  # climatology years
    obs += [("2026-11-13", 500), ("2026-11-15", 1000)]  # persistence source, truth
    (tmp_path / "cdec_inflow").mkdir()
    (tmp_path / "cdec_inflow" / "FOL.csv").write_text("date,cfs\n" + "".join(f"{d},{v}\n" for d, v in obs))
    members = [0.9 + 0.01 * i for i in range(21)]  # kcfs, 0.9..1.1 -> median 1000 cfs
    body = (
        # issued 2026-11-14 12Z: the analysis, the issue day (not scored), then lead 1 in the row stamped a day late
        "GMT" + ",FOLC1" * 21 + "\n" + ",SQME" * 21 + "\n2026-11-14 12:00:00" + ",0.5" * 21 + "\n"
        "2026-11-15 12:00:00" + ",0.7" * 21 + "\n2026-11-16 12:00:00," + ",".join(map(str, members)) + "\n"
    )
    (tmp_path / "hefs_daily" / "FOLC1").mkdir(parents=True)
    (tmp_path / "hefs_daily" / "FOLC1" / "20261114T123000Z.gz").write_bytes(gzip.compress(body.encode()))
    d = tmp_path / "forecasts" / "embalse_v1" / "FOLC1"
    d.mkdir(parents=True)
    (d / "2026-11-14.csv").write_text("date,lead,q05,q50,q95\n2026-11-15,1,900,1000,1100\n2026-11-16,2,500,600,700\n")
    rows = score.score(tmp_path)
    assert [(r["product"], r["lead"]) for r in rows] == [
        ("hefs", 1),
        ("embalse_v1", 1),
    ]  # lead 2 has no observation yet
    r = rows[0]
    assert (r["lid"], r["lead"], r["obs_cfs"], r["crps_persistence"], r["in90"]) == ("FOLC1", 1, 1000, 500, 1)
    assert r["crps"] == round(score.crps([x * 1000 for x in members], 1000), 1) < 50
    assert rows[1]["crps"] == round(score.crps([900, 1000, 1100], 1000), 1) and rows[1]["in90"] == 1
