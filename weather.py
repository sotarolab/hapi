"""Archive the weather forecast at every point the site shows: hourly precipitation and freezing level from
four models, and integrated vapor transport (IVT) computed from GFS winds and humidity on pressure levels.
Source: Open-Meteo (no key). One derived file per point and run, data/weather/<point>/<UTC time>.gz;
site.py turns the newest into the page's weather panel and the atmospheric river scale.

Run: python weather.py [out_dir]   (default: data/)
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from archive import fetch, save
from points import GAUGES, RESERVOIRS

MODELS = {"gfs_seamless": "GFS", "ecmwf_ifs025": "ECMWF", "icon_seamless": "ICON", "ncep_nbm_conus": "NBM"}
IVT_MODEL = "gfs_seamless"  # the only one Open-Meteo serves with every level below
LEVELS = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300]  # hPa, surface upward
LEVEL_VARS = ["wind_speed", "wind_direction", "relative_humidity", "temperature"]
GRAVITY = 9.81
FRESH_HOURS = 5  # Open-Meteo refreshes each 6 h cycle; the archive job runs hourly for the observed flow

API = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&forecast_days=7&timezone=UTC"
SURFACE = API + "&hourly=precipitation,freezing_level_height&models=" + ",".join(MODELS)
PROFILE = (
    API
    + "&wind_speed_unit=ms&models="
    + IVT_MODEL
    + "&hourly="
    + ",".join(f"{v}_{p}hPa" for p in LEVELS for v in LEVEL_VARS)
)


def ivt(profile: list[tuple]) -> float | None:
    """IVT magnitude (kg/m/s) from one sounding. Rows are (pressure hPa, wind speed m/s, wind direction deg,
    relative humidity %, temperature C), ordered from the surface upward. None if any value is missing.

    Specific humidity comes from RH and temperature (Bolton 1980); the moisture flux q*u, q*v is integrated
    over pressure by the trapezoid rule and divided by g."""
    flux = []
    for p, speed, direction, rh, temp in profile:
        if None in (speed, direction, rh, temp):
            return None
        e = min(max(rh, 0) / 100 * 6.112 * math.exp(17.67 * temp / (temp + 243.5)), p * 0.99)  # vapor pressure, hPa
        q = 0.622 * e / (p - 0.378 * e)
        a = math.radians(direction)  # the direction the wind blows from
        flux.append((p * 100, -q * speed * math.sin(a), -q * speed * math.cos(a)))
    qu, qv = (sum((lo[k] + hi[k]) / 2 * (lo[0] - hi[0]) for lo, hi in zip(flux, flux[1:])) / GRAVITY for k in (1, 2))
    return math.hypot(qu, qv)


def derive(surface: dict, profile: dict) -> dict:
    """The two Open-Meteo answers reduced to what is archived: hourly times (UTC), precipitation (mm) and
    freezing level (m) per model, and IVT (kg/m/s). A model with no values for a variable is left out."""
    s, p = surface["hourly"], profile["hourly"]
    if s["time"] != p["time"]:
        raise ValueError("surface and profile times differ")
    by_model = lambda var: {
        name: s[f"{var}_{m}"] for m, name in MODELS.items() if any(v is not None for v in s.get(f"{var}_{m}", []))
    }
    values = [
        ivt([(lev, *(p[f"{v}_{lev}hPa"][i] for v in LEVEL_VARS)) for lev in LEVELS]) for i in range(len(p["time"]))
    ]
    return {
        "times": s["time"],
        "precip_mm": by_model("precipitation"),
        "freezing_m": by_model("freezing_level_height"),
        "ivt": [None if v is None else round(v) for v in values],
    }


def fresh(out: Path, lid: str, now: datetime) -> bool:
    """True when the point's newest archived forecast is under FRESH_HOURS old (the stem is its UTC fetch time)."""
    files = sorted((out / "weather" / lid).glob("*.gz")) if (out / "weather" / lid).is_dir() else []
    return bool(files) and now - datetime.strptime(files[-1].stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC) < timedelta(
        hours=FRESH_HOURS
    )


def main(out: Path) -> int:
    now = datetime.now(UTC)
    saved = failed = skipped = 0
    points = {lid: v[1:3] for lid, v in {**RESERVOIRS, **GAUGES}.items()}
    for lid, (lat, lon) in points.items():
        if fresh(out, lid, now):
            skipped += 1
            continue
        bodies = [fetch(url.format(lat=lat, lon=lon)) for url in (SURFACE, PROFILE)]
        try:
            body = json.dumps(
                derive(*(json.loads(b or b"") for b in bodies))
            ).encode()  # a failed fetch reads as bad JSON
        except (TypeError, ValueError, KeyError) as e:  # a failed fetch, bad JSON, or Open-Meteo's error object
            failed += 1
            print(f"BAD PAYLOAD {lid} weather: {e!r}", file=sys.stderr)
            continue
        saved += save(out, lid, "weather", body, now) is not None
    print(f"{now:%Y-%m-%dT%H:%MZ} weather: saved {saved} new, {failed} failed, {skipped} still fresh, of {len(points)}")
    return 0  # the page shows no weather panel for a point without a file; never block the official archive


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data")))
