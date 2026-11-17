# hapi

The public record of California river-flow and reservoir-inflow forecasts: it archives the official
forecasts, receives model forecasts from [caudal](https://github.com/sotarolab/caudal) as files,
scores all of them against observations and serves the result as a static page. How it fits
together is `docs/ARCHITECTURE.md`.

## Rules

- **Archive wide, score narrow.** Every product for every point is saved on every run.
- **Never revise.** A forecast file is written once. A changed model is a new product.
- **Before the outcome.** A model forecast counts only if it reached the `data` branch before the
  day it predicts.
- **The referee does not import the player.** The root scripts use only the standard library and
  each other, and never import caudal; `tests/test_stdlib_only.py` enforces it. Dev tools live in
  `[dependency-groups]` in `pyproject.toml`.
- **Python computes, the page draws.** Every number, label, unit and colour on the page is
  written by `site.py`. The owner reads Python, not TypeScript.
- **`data` is written only by the hourly job and caudal's issue job.** Never commit to it by hand.
- **A change ships with its test** in the same pull request.
- **Plain prose**: no em dashes, no hedging, no claim without a number or a reference behind it.
  Keys and credentials never enter the repository. The repository is public.

## Commands

    uv sync                              # dev tools into .venv; a dependency change ships with `make lock`
    make qc PY=.venv/bin/python          # ruff + pyright + pytest: what CI and the Stop hook run
    python archive.py data               # each script takes the data folder; see README.md for the order
    cd app && npm ci && npm test && npm run build

## Process

The owner owns the process.

- **Plan first.** Anything beyond a one-file fix starts as a plan the owner approves.
- **One issue, one branch, one pull request.** `/issue` opens the issue, with the tests to write
  listed in it. Work happens on a branch named `<issue number>-<slug>`. `/pr` runs `make qc`,
  reviews the diff, fills the template (its body says `Closes #<n>` and its Not checked section is
  never empty), pushes the branch and opens the pull request.
- **The owner reviews and merges.** Claude may push feature branches and open issues and pull
  requests. Claude never pushes to `main` or `data`, never force pushes and never merges; the
  settings deny the last two.
- **Attribution.** A commit Claude wrote ends with the Claude co-author line.
- **Say what was not checked.** End a piece of work with what was skipped and what is uncertain.
