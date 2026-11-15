# inflow-ledger

A public, timestamped record of river-flow and reservoir-inflow forecasts for California,
scored against the official forecasts.

Step 1 (this commit): `archive.py` saves the official products that cannot be backfilled:
the CNRFC HEFS ensembles (17 reservoir inflow points, 12 flood gauges) and the NWS official
forecast for the flood gauges. The workflow runs it every 6 hours and commits to the `data` branch.

    python archive.py          # writes data/<product>/<point>/<UTC time>.gz, skipping unchanged files
    python -m pytest tests

One-time setup after creating the GitHub repo: push `main`, then create an empty `data` branch
(`git switch --orphan data && git commit --allow-empty -m "data" && git push -u origin data`).
