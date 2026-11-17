"""The contract a model forecast meets to enter the record, and its check. A forecast is
forecasts/<model>/<point>/<issue date>.csv: a header `date,lead` followed by one or more quantile columns
named qNN in increasing order, then one row per lead day in cfs. A product may carry
forecasts/<model>/MODEL.json saying what issued it. The model's own repository checks the same rules before
it writes; the two are kept equal by a shared fixture, a real issued file.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from datetime import date, timedelta
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


def check_forecast(path: Path) -> list[str]:
    """The reasons the file breaks the contract; empty when it holds."""
    try:
        issue = date.fromisoformat(path.stem)
    except ValueError:
        return [f"the file name {path.name} is not an issue date"]
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return ["no forecast rows"]
    header, quantiles = rows[0], rows[0][2:]
    named = all(QUANTILE.match(q) for q in quantiles)
    if header[:2] != ["date", "lead"] or not quantiles or not named or quantiles != sorted(set(quantiles)):
        return [f"the header {','.join(header)} is not date, lead and increasing qNN columns"]
    errors = []
    for n, r in enumerate(rows[1:], 1):
        try:
            day, lead, values = date.fromisoformat(r[0]), int(r[1]), [float(v) for v in r[2:]]
        except (ValueError, IndexError):
            errors.append(f"row {n} does not parse")
            continue
        if len(r) != len(header):
            errors.append(f"row {n} has {len(r)} values for {len(header)} columns")
        elif lead != n:
            errors.append(f"row {n} has lead {lead}: leads run 1, 2, ... with none missing")
        elif day != issue + timedelta(days=lead):
            errors.append(f"row {n}: {day} is not the issue date {issue} plus {lead} days")
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
