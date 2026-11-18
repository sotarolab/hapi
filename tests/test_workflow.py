"""The hourly job (.github/workflows/archive.yml), read as text: a failed feed must not cost the hour's archive."""

import re
from pathlib import Path

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "archive.yml").read_text()


def step(command: str) -> str:
    """The lines of the step that runs `command`, up to the next step."""
    start = WORKFLOW.index(command)
    return WORKFLOW[start : WORKFLOW.find("\n      - ", start)]


def test_a_failed_feed_does_not_stop_the_hourly_run():
    for script in ("weather.py", "ivt_field.py", "live.py"):  # each reads feeds that drop a request now and then
        assert "continue-on-error: true" in step(f"run: python {script}"), script
    for script in ("archive.py", "score.py", "site.py"):  # a failure here is a fault of ours and must show
        assert "continue-on-error" not in step(f"run: python {script}"), script
    assert "if: ${{ !cancelled() }}" in step("run: python site.py")
    commit = step("name: Commit new files")
    assert "if: ${{ !cancelled() }}" in commit and re.search(r"git add data\n", commit) and "git push" in commit
