"""The contract a model forecast meets to enter the record, and its check. A daily forecast is
forecasts/<model>/<point>/<issue date>.csv: a header `date,lead` followed by one or more quantile columns
named qNN in increasing order, then one row per lead day in cfs. An hourly forecast is named for its issue
hour, <YYYY-MM-DD>T<HH>Z.csv, its header starts `time,lead`, and it has one row per lead hour, each time
written as <YYYY-MM-DD>T<HH>:00Z. A product may carry
forecasts/<model>/MODEL.json saying what issued it. The model's own repository checks the same rules before
it writes; the two are kept equal by a shared fixture, a real issued file.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

QUANTILE = re.compile(r"^q\d{2}$")
MANIFEST_KEYS = (
    "model",
    "points",
    "quantiles",
    "leads",
    "issued_since",
    "caudal_commit",
    "checkpoint_sha256",
    "description",
)


# What the file name's form says about the file: the form of its row times, the step between leads, the name
# of the first column, and the words for the messages.
DAILY = ("%Y-%m-%d", "%Y-%m-%d", timedelta(days=1), "date", "date", "days")
HOURLY = ("%Y-%m-%dT%HZ", "%Y-%m-%dT%H:%MZ", timedelta(hours=1), "time", "hour", "hours")


def issued(path: Path) -> tuple[datetime, tuple] | None:
    """The issue time and the kind (DAILY or HOURLY) of a forecast file, from its name."""
    for kind in (DAILY, HOURLY):
        try:
            return datetime.strptime(path.stem, kind[0]), kind
        except ValueError:
            pass
    return None


def check_forecast(path: Path) -> list[str]:
    """The reasons the file breaks the contract; empty when it holds."""
    found = issued(path)
    if found is None:
        return [f"the file name {path.name} is not an issue date or an issue hour"]
    issue, (stem, form, step, column, word, unit) = found
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return ["no forecast rows"]
    header, quantiles = rows[0], rows[0][2:]
    named = all(QUANTILE.match(q) for q in quantiles)
    if header[:2] != [column, "lead"] or not quantiles or not named or quantiles != sorted(set(quantiles)):
        return [f"the header {','.join(header)} is not {column}, lead and increasing qNN columns"]
    errors = []
    for n, r in enumerate(rows[1:], 1):
        try:
            when, lead, values = datetime.strptime(r[0], form), int(r[1]), [float(v) for v in r[2:]]
        except (ValueError, IndexError):
            errors.append(f"row {n} does not parse")
            continue
        if len(r) != len(header):
            errors.append(f"row {n} has {len(r)} values for {len(header)} columns")
        elif lead != n:
            errors.append(f"row {n} has lead {lead}: leads run 1, 2, ... with none missing")
        elif when != issue + step * lead:
            errors.append(f"row {n}: {r[0]} is not the issue {word} {issue.strftime(stem)} plus {lead} {unit}")
        elif any(not math.isfinite(v) or v < 0 for v in values):
            errors.append(f"row {n} has a negative or non-finite value")
        elif values != sorted(values):
            errors.append(f"row {n}: the quantiles decrease")
    return errors


def read_manifest(path: Path) -> dict | None:
    """The product's MODEL.json when it exists and has every key; None otherwise, said on stderr if it is bad."""
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text())
    except ValueError:
        manifest = None
    missing = [k for k in MANIFEST_KEYS if k not in manifest] if isinstance(manifest, dict) else ["a JSON object"]
    if missing:
        print(f"BAD MANIFEST {path}: missing {', '.join(missing)}", file=sys.stderr)
        return None
    return manifest
