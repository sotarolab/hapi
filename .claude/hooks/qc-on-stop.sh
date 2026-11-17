#!/bin/bash
# Stop hook: when Python files have uncommitted changes, run `make qc` before the turn ends.
# Exit 2 hands the failure back to Claude instead of letting it stop on red.
# The interpreter comes from PY (set it in .claude/settings.local.json under "env"), else `python`.

input=$(cat)

# Second pass after a block: let the turn end, so a check that keeps failing cannot loop forever.
if [ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Nothing to check on a turn that changed no code.
if [ -z "$(git status --porcelain -- '*.py' pyproject.toml 2>/dev/null)" ]; then
  exit 0
fi

if ! out=$(make -s qc PY="${PY:-python}" 2>&1); then
  printf 'make qc failed. Fix it before finishing, or say why it cannot be fixed.\n%s\n' \
    "$(printf '%s' "$out" | tail -25)" >&2
  exit 2
fi
exit 0
