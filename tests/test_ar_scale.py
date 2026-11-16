"""The Ralph et al. (2019) AR classification. Each case pins one published rule that is easy to get wrong: the
1250 tier, the demote/promote duration scheme, the inclusive 48 h boundary, the ungraded "Weak AR" cell."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ar_scale import IVT_AR_THRESHOLD, _duration_shift, _ivt_tier, _longest_run_hours, classify_ar

STEP = 6.0  # hours


def test_ivt_tiers_match_published_thresholds():
    assert _ivt_tier(250) == 1
    assert _ivt_tier(499) == 1
    assert _ivt_tier(500) == 2
    assert _ivt_tier(750) == 3
    assert _ivt_tier(1000) == 4
    assert _ivt_tier(1249) == 4
    assert _ivt_tier(1250) == 5


def test_duration_shift_is_demote_baseline_promote():
    assert _duration_shift(18) == -1
    assert _duration_shift(24) == 0
    assert _duration_shift(47.9) == 0
    assert _duration_shift(48) == 1   # inclusive: Table 2's column is headed ">=48", not ">48"
    assert _duration_shift(96) == 1   # no growing bonus beyond +1


def test_longest_run_is_sustained_not_total():
    # Two separate 12 h pulses with a lull: the longest single run is 12 h, not 24 h above the threshold.
    assert _longest_run_hours([300, 300, 100, 300, 300], STEP) == 12.0


def test_no_ar_conditions():
    result = classify_ar([100, 200, 240], STEP)
    assert result.category == 0
    assert result.label == "No AR conditions"
    assert result.onset_time is None and result.offset_time is None


def test_weak_ar_cell_is_ungraded_not_cat1():
    # IVT 250-500 sustained under 24 h: the one cell the paper leaves off the numbered scale.
    result = classify_ar([300, 300, 100], STEP)  # 12 h run
    assert result.category == 0
    assert result.label == "Weak (below CAT 1)"


def test_baseline_duration_keeps_preliminary_rank():
    assert classify_ar([300, 300, 300, 300, 100], STEP).category == 1  # 24 h run, tier 1


def test_exactly_48h_promotes():
    result = classify_ar([300] * 8, STEP)  # 8 consecutive 6 h steps = exactly 48 h
    assert result.duration_hours == 48.0
    assert result.category == 2  # tier 1 promoted by the inclusive >=48 h rule


def test_hourly_steps_count_hours():
    assert classify_ar([300] * 47, 1.0).category == 1 and classify_ar([300] * 48, 1.0).category == 2


def test_short_strong_ar_demoted():
    assert classify_ar([800, 800, 100], STEP).category == 2  # tier 3, 12 h run


def test_exceptional_clipped_at_5():
    result = classify_ar([1300] * 9, STEP)  # tier 5, 54 h run: 5 + 1 clips to 5
    assert result.category == 5
    assert result.label.startswith("CAT 5")


def test_onset_offset_bracket_all_pulses():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    times = [t0 + timedelta(hours=6 * i) for i in range(5)]
    result = classify_ar([100, 300, 100, 300, 100], STEP, valid_times=times)
    assert result.onset_time == times[1]   # first crossing
    assert result.offset_time == times[3]  # last crossing, across the lull in between
    assert result.max_ivt == 300
    assert result.duration_hours == 6.0


def test_threshold_is_inclusive():
    assert classify_ar([IVT_AR_THRESHOLD] * 5, STEP).category >= 1
