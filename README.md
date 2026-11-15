# inflow-ledger

A public, timestamped record of river-flow and reservoir-inflow forecasts for California,
scored against the official forecasts.

Step 1: `archive.py` saves the official products that cannot be backfilled:
the CNRFC HEFS ensembles (17 reservoir inflow points, 12 flood gauges) and the NWS official
forecast for the flood gauges. The workflow runs it every 6 hours and commits to the `data` branch.

Step 2: `score.py` fetches observed daily reservoir inflow from CDEC (sensor 76) for the 11 points with
clean records and scores every archived HEFS daily ensemble at leads 1-14 days: fair CRPS, 90% coverage,
and the CRPS of two baselines, persistence (last observed day) and day-of-year climatology (all prior
years as an ensemble). One row per forecast-day in `data/scores/inflow_daily.csv`; the pooled table
is printed. Flood gauges are archived but not yet scored.

    python archive.py          # writes data/<product>/<point>/<UTC time>.gz, skipping unchanged files
    python score.py            # refreshes data/cdec_inflow/<station>.csv, writes data/scores/inflow_daily.csv
    python -m pytest tests
    jupyter lab notebooks/ledger.ipynb   # observed inflow with the newest HEFS fan per reservoir, and the score table

One-time setup after creating the GitHub repo: push `main`, then create an empty `data` branch
(`git switch --orphan data && git commit --allow-empty -m "data" && git push -u origin data`).
