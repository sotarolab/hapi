# hapi

Live at https://sotarolab.github.io/hapi/. How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

A public, timestamped record of river-flow and reservoir-inflow forecasts for California,
scored against the official forecasts.

Step 1: `archive.py` saves the official products as they are issued:
the CNRFC HEFS ensembles (17 reservoir inflow points, 12 flood gauges), the NWS official
forecast for the flood gauges, and the National Water Model's short-range and medium-range forecasts at
each gauge's river reach. The hourly workflow runs it and commits to the `data` branch.

Step 2: `score.py` fetches observed daily reservoir inflow from CDEC (sensor 76) for the 11 points with
clean records and scores every archived HEFS daily ensemble at leads 1-14 days: fair CRPS, 90% coverage,
and the CRPS of two baselines, persistence (last observed day) and day-of-year climatology (all prior
years as an ensemble). A daily HEFS row stamped 12Z is the mean of the 24 hours before it, so it is paired
with the day before its stamp; lead 1 is the day after the issue, read from the row stamped two days after
it. One row per forecast-day in `data/scores/inflow_daily.csv`; the pooled table
is printed. Model forecasts dropped under `data/forecasts/<model>/<point>/<issue date>.csv` (columns
`date,lead,q05,...`) are scored the same way, as an ensemble of their quantiles. An hourly product is named for
its issue hour (`<date>T<HH>Z.csv`, columns `time,lead,q05,...`); `site.py` draws its newest forecast on the
point's chart and it is not scored yet. Flood gauges are archived but not yet scored.

Hindcast: CNRFC keeps every 12Z HEFS issue since January 2014 as dated zips. `retro.py` fetches the issue day
and the 14 leads of each one for the reservoir points into a separate folder with the same layout, and
`score.py` scores that folder unchanged. A hindcast is weaker evidence than the live record, because nobody
can show when a hindcast forecast was made. The folder is not read by the page and never goes to the `data`
branch.

First model product: `quantile_inflow_v1_s0`, a regional quantile LSTM on Open-Meteo forcing from the
`caudal` package, issuing 14-day forecasts for the 11 reservoirs since 2026-11-15. Its retrospective
skill on water years 2016-2025 is in that package; the live score is this ledger.

    python archive.py          # writes data/<product>/<point>/<UTC time>.gz, skipping unchanged files
    python weather.py          # writes data/weather/<point>/<UTC time>.gz: the weather forecast at each point
    python ivt_field.py        # writes data/ivt_gfs/<cycle>.gz: the GFS IVT field, once per forecast cycle
    python score.py            # refreshes data/cdec_inflow/<station>.csv, writes data/scores/inflow_daily.csv
    python retro.py hindcast 2015-10-01 2025-09-30 && python score.py hindcast   # past HEFS issues, scored apart
    python -m pytest tests
    jupyter lab notebooks/ledger.ipynb   # observed inflow with the newest HEFS fan per reservoir, and the score table

Weather: `weather.py` runs with the archive, refetching a point once its newest file is 5 hours old, and saves the forecast at every point from Open-Meteo: hourly
precipitation and freezing level from GFS, ECMWF IFS, ICON and NBM, and integrated vapor transport (IVT)
computed from GFS winds and humidity on pressure levels. `ar_scale.py` grades the IVT on the atmospheric river
scale of Ralph et al. (2019).

IVT field: `ivt_field.py` runs with the archive and saves the GFS forecast of IVT over the northeast Pacific
(20 to 55 N, 170 to 110 W, 1 degree) as two components, one file per forecast cycle under `data/ivt_gfs/`:
hours 0 to 120 every 6 hours. It reads NOAA's GRIB filter and decodes the simple-packed GRIB2 messages itself,
with the standard library. `site.py` writes `data/site/ivt.json` from it for the map: the past two days and
the forecast, with the legend.

Live: `live.py` rewrites `data/live/<lid>.json` every run with the week's hourly observed flow at each point
(at the reservoirs a centred 24-hour mean of CDEC's hourly computed inflow, written only where the hourly values vary less than their mean; at the gauges the NWS observed series) and each gauge's NWS flood
categories in cfs, read off the gauge's NWS rating curve where NWPS gives only the stage.

Observations as published: the feeds revise their values, so two logs keep what was first published. `score.py`
appends to `data/cdec_inflow_log/<station>.csv` each day's inflow the first time it appears and each time it
changes (`date,cfs,seen`), and `live.py` does the same for the gauges' observed flow and stage in
`data/gauge_obs/<gauge>/<day>.csv` (`time,cfs,stage_ft,seen`). Rows are only added.

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
