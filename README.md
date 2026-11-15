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
is printed. Model forecasts dropped under `data/forecasts/<model>/<point>/<issue date>.csv` (columns
`date,lead,q05,...`) are scored the same way, as an ensemble of their quantiles. Flood gauges are archived
but not yet scored.

First model product: `quantile_inflow_v1_s0`, a regional quantile LSTM on Open-Meteo forcing from the
private `embalse` package, issuing 14-day forecasts for the 11 reservoirs since 2026-11-15. Its retrospective
skill on water years 2016-2025 is in that package; the live score is this ledger.

    python archive.py          # writes data/<product>/<point>/<UTC time>.gz, skipping unchanged files
    python score.py            # refreshes data/cdec_inflow/<station>.csv, writes data/scores/inflow_daily.csv
    python -m pytest tests
    jupyter lab notebooks/ledger.ipynb   # observed inflow with the newest HEFS fan per reservoir, and the score table

The archive and scores live on the `data` branch (github.com/sotarolab/inflow-ledger/tree/data).
