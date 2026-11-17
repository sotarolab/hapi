# hapi

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
`caudal` package, issuing 14-day forecasts for the 11 reservoirs since 2026-11-15. Its retrospective
skill on water years 2016-2025 is in that package; the live score is this ledger.

    python archive.py          # writes data/<product>/<point>/<UTC time>.gz, skipping unchanged files
    python weather.py          # writes data/weather/<point>/<UTC time>.gz: the weather forecast at each point
    python score.py            # refreshes data/cdec_inflow/<station>.csv, writes data/scores/inflow_daily.csv
    python -m pytest tests
    jupyter lab notebooks/ledger.ipynb   # observed inflow with the newest HEFS fan per reservoir, and the score table

Weather: `weather.py` runs with the archive, refetching a point once its newest file is 5 hours old, and saves the forecast at every point from Open-Meteo: hourly
precipitation and freezing level from GFS, ECMWF IFS, ICON and NBM, and integrated vapor transport (IVT)
computed from GFS winds and humidity on pressure levels. `ar_scale.py` grades the IVT on the atmospheric river
scale of Ralph et al. (2019).

Live: `live.py` rewrites `data/live/<lid>.json` every run with the week's hourly observed flow at each point
(at the reservoirs a centred 24-hour mean of CDEC's hourly computed inflow, written only where the hourly values vary less than their mean; at the gauges the NWS observed series) and each gauge's NWS flood
categories in cfs, read off the gauge's NWS rating curve where NWPS gives only the stage.

Step 3: `site.py` digests the archive into `data/site/` (points, the newest fans, the scorecards, the weather
panel) and `app/` is the page that reads it: a map of the points with radar and satellite overlays, each point's
observed inflow with the HEFS fan, the model fans and the NWS official forecast, its weather and AR scale,
satellite and radar loops, and a Lab tab with the record and the scorecards. Every number, label and unit on the
weather panel is written by `site.py`; the page only draws it. It is static (Vite + React, Leaflet, uPlot),
deployed to GitHub Pages by `.github/workflows/pages.yml`, and reads the data branch directly.

    cd app && npm ci && npm test && npm run build
    (cd data/site && python -m http.server 8070) &   # then, for the dev server against local data (SITEDATA=http://localhost:<port> if 8070 is busy):
    VITE_DATA_BASE=/sitedata npm run dev

The archive and scores live on the `data` branch (github.com/sotarolab/hapi/tree/data).
