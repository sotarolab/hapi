import io
import zipfile
from datetime import date, timedelta

import retro
import score

DAY = date(2019, 2, 26)


def group_file(names: list[str], rows: int = 366, first: date = DAY) -> list[str]:
    """A CNRFC group file: the names row, the units row, then one row per day in kcfs."""
    out = [",".join(["GMT", *names]), ",".join(["", *["QINE"] * len(names)])]
    for i in range(rows):
        values = [f"{i + 1}.{j * 7919 % 1000:03d}" for j in range(len(names))]
        out.append(",".join([f"{first + timedelta(days=i)} 12:00:00", *values]))
    return out


def zipped(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("group_hefs_csv_daily.csv", "\n".join(lines) + "\n")
    return buf.getvalue()


def test_head_reads_the_first_rows_and_leaves_the_rest():
    lines = group_file([f"P{i:02d}C1" for i in range(20) for _ in range(59)])
    stream = io.BytesIO(zipped(lines))
    assert retro.head(stream, retro.ROWS) == lines[: retro.ROWS]
    assert stream.tell() < len(stream.getvalue()) / 2


def test_head_rejects_a_page_that_is_not_a_zip():
    assert retro.head(io.BytesIO(b"<!DOCTYPE html><html><body>404 Not Found</body></html>"), retro.ROWS) is None


def test_head_gives_nothing_for_a_file_shorter_than_asked():
    assert retro.head(io.BytesIO(zipped(group_file(["FOLC1"], 5))), retro.ROWS) is None


def test_split_finds_a_point_under_either_name():
    old = retro.split(group_file(["ORDC1", "ORDC1", "NBBC1L"], 3), ["ORDC1", "NBBC1"])
    new = retro.split(group_file(["ORDC1F", "ORDC1F", "NBBC1L"], 3), ["ORDC1", "NBBC1"])
    assert list(old) == list(new) == ["ORDC1"]
    assert old["ORDC1"].splitlines()[2] == b"2019-02-26 12:00:00,1.000,1.919"
    assert retro.split(group_file(["ORDC1", "ORDC1F"], 3), ["ORDC1"]) == {}  # both names: not known which to take


def run(tmp_path, calls: list) -> int:
    def fetch(day, group):
        calls.append((day, group))
        return group_file([x for lid in retro.GROUPS[group] for x in [lid] * 3], retro.ROWS - 2, day)

    return retro.main(tmp_path, DAY, DAY, fetch)


def test_written_file_is_read_by_the_scorer(tmp_path):
    assert run(tmp_path, []) == 0
    [(product, issue, fc)] = score.forecasts(tmp_path, "FOLC1")
    assert (product, issue, len(fc)) == ("hefs", DAY, 2 + max(score.LEADS))  # the issue day, the leads, one day more
    assert fc[min(fc)] == [1000.0, 1919.0, 1838.0]  # kcfs in the file, cfs for the scorer


def test_issue_days_already_saved_are_not_fetched_again(tmp_path):
    calls = []
    run(tmp_path, calls)
    assert len(calls) == len(retro.GROUPS)
    run(tmp_path, calls)
    assert len(calls) == len(retro.GROUPS)
