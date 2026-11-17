"""Atmospheric river strength at a point on the AR1-5 scale of Ralph et al. (2019), from a time series of
integrated vapor transport (IVT).

Ralph, F.M., J.J. Rutz, J.M. Cordeira, M. Dettinger, M. Anderson, D. Reynolds, L.J. Schick, and C.
Smallcomb, 2019: A Scale to Characterize the Strength and Impacts of Atmospheric Rivers. Bull. Amer.
Meteor. Soc., 100, 269-289. The rules below follow its Table 2 and Fig. 4.
"""

from dataclasses import dataclass

IVT_AR_THRESHOLD = 250.0  # kg/m/s, the floor of AR conditions

AR_LABELS = {1: "CAT 1: Weak", 2: "CAT 2: Moderate", 3: "CAT 3: Strong", 4: "CAT 4: Extreme", 5: "CAT 5: Exceptional"}
AR_IMPACT = {
    1: "primarily beneficial",
    2: "mostly beneficial, some hazard",
    3: "balance of beneficial and hazardous",
    4: "mostly hazardous, some benefit",
    5: "primarily hazardous",
}


@dataclass
class ARClassification:
    max_ivt: float
    duration_hours: float
    # 1-5 for a graded AR. 0 is either no AR conditions at all (onset_time is None) or the paper's ungraded
    # "Weak AR" cell (onset_time is set): AR conditions were reached but rank below Cat 1.
    category: int
    label: str
    impact: str
    # First and last point at or above the threshold over the whole series, not only the longest run: an AR
    # often comes in pulses with a lull between, and arrival and departure bracket all of them.
    onset_time: object = None
    offset_time: object = None


def _ivt_tier(max_ivt: float) -> int:
    """Preliminary rank 1-5 from peak IVT alone (250/500/750/1000/1250 kg/m/s), before the duration shift.
    Only called once max_ivt has cleared IVT_AR_THRESHOLD, so it returns at least 1."""
    if max_ivt >= 1250:
        return 5
    if max_ivt >= 1000:
        return 4
    if max_ivt >= 750:
        return 3
    if max_ivt >= 500:
        return 2
    return 1


def _duration_shift(duration_hours: float) -> int:
    """-1/0/+1: under 24 h demotes the preliminary rank by one, 24-48 h leaves it, 48 h or more promotes it
    by one (48 itself included: Table 2's column is headed ">=48"). Not a bonus that grows with duration."""
    if duration_hours < 24:
        return -1
    if duration_hours >= 48:
        return 1
    return 0


def _longest_run_hours(ivt_values, time_step_hours: float, threshold: float = IVT_AR_THRESHOLD) -> float:
    """Longest single unbroken stretch of IVT at or above the threshold, in hours. Not the total time above
    it: an on-and-off pattern should not score like one sustained episode."""
    longest = current = 0.0
    for v in ivt_values:
        if v >= threshold:
            current += time_step_hours
            longest = max(longest, current)
        else:
            current = 0.0
    return longest


def _first_last_crossing(ivt_values, valid_times, threshold: float = IVT_AR_THRESHOLD):
    """Times of the first and last point at or above the threshold in the whole series; None, None if it is
    never reached."""
    crossing_idxs = [i for i, v in enumerate(ivt_values) if v >= threshold]
    if not crossing_idxs:
        return None, None
    return valid_times[crossing_idxs[0]], valid_times[crossing_idxs[-1]]


def classify_ar(ivt_values, time_step_hours: float, valid_times=None) -> ARClassification:
    """Classify a single-point IVT time series on the Ralph et al. (2019) scale.

    ivt_values: IVT (kg/m/s) at one point, in time order. The paper takes peak IVT from a 3-hour mean; hapi
    passes hourly instantaneous values, so a sharp, brief spike can read slightly higher here.
    time_step_hours: spacing between consecutive values; duration is resolved to multiples of it.
    valid_times: optional times aligned with ivt_values; when given, onset_time and offset_time are set.
    """
    max_ivt = max(ivt_values) if len(ivt_values) else 0.0
    duration = _longest_run_hours(ivt_values, time_step_hours)
    onset_time, offset_time = _first_last_crossing(ivt_values, valid_times) if valid_times is not None else (None, None)

    if max_ivt < IVT_AR_THRESHOLD:
        return ARClassification(max_ivt, duration, 0, "No AR conditions", "n/a")

    preliminary = _ivt_tier(max_ivt) + _duration_shift(duration)
    if preliminary < 1:
        # Only tier 1 (250-500 kg/m/s) lasting under 24 h lands here: the one cell Table 2 and Fig. 4 leave
        # off the numbered scale ("Weak AR"). AR conditions were real, so it is not "No AR conditions", but
        # it is weaker than a graded Cat 1 and must not be clipped up to it.
        return ARClassification(
            max_ivt, duration, 0, "Weak (below CAT 1)", "primarily beneficial", onset_time, offset_time
        )

    category = min(5, preliminary)
    return ARClassification(
        max_ivt, duration, category, AR_LABELS[category], AR_IMPACT[category], onset_time, offset_time
    )
