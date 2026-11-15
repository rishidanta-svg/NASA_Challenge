"""NOAA CO-OPS station observations and separately labeled tide predictions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
from threading import Lock
from time import monotonic

import httpx

URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
STATION = "8651370"
PRODUCTS = {
    "water_level": [("water_level", "Water level", "m", "v")],
    "wind": [("wind_speed", "Wind speed", "m/s", "s"), ("wind_gust", "Wind gust", "m/s", "g")],
    "air_temperature": [("air_temperature", "Air temperature", "°C", "v")],
    "water_temperature": [("water_temperature", "Water temperature", "°C", "v")],
    "air_pressure": [("air_pressure", "Barometric pressure", "hPa", "v")],
}


def number(value):
    try:
        val = float(value)
        return val if math.isfinite(val) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch(client, product, now):
    params = {"station": STATION, "units": "metric", "time_zone": "gmt", "format": "json",
              "application": "POLTERGEIST_NASA_SpaceApps", "product": product}
    if product in ("water_level", "predictions"):
        params["datum"] = "NAVD"
    if product == "predictions":
        params.update(begin_date=now.strftime("%Y%m%d %H:%M"), range="30", interval="hilo")
    else:
        params["date"] = "latest"
    try:
        response = client.get(URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "error" in payload:
            return [], "NOAA reported this product unavailable"
        return payload.get("predictions" if product == "predictions" else "data", []), None
    except (httpx.HTTPError, ValueError):
        return [], "NOAA upstream request failed"


def observation(product, field, row, error=None):
    variable, label, units, key = field
    when = timestamp(row.get("t"))
    val = number(row.get(key)) if when else None
    return {"variable": variable, "label": label, "units": units, "value": val,
            "observed_at": when.isoformat() if when else None,
            "kind": "prediction" if product == "predictions" else "observation",
            "station_id": STATION, "station_name": "Duck, NC", "provider": "NOAA CO-OPS",
            "datum": "NAVD88" if product in ("water_level", "predictions") else None,
            "qc_flag": row.get("f"),
            "quality": {"v":"verified", "p":"preliminary"}.get(row.get("q"), "unknown"),
            "source_url": f"https://tidesandcurrents.noaa.gov/stationhome.html?id={STATION}",
            "extra": {"product": product, **({"direction_deg_true": number(row.get("d")),
                      "direction_cardinal": row.get("dr")} if variable == "wind_speed" else {})},
            "error": (error or "Station did not publish a current value") if val is None else None}


class Environment:
    def __init__(self):
        self.lock = Lock()
        self.cached = None
        self.expires = 0

    def latest(self):
        with self.lock:
            if monotonic() < self.expires:
                return self.cached
            now = datetime.now(timezone.utc)
            names = (*PRODUCTS, "predictions")
            with httpx.Client(timeout=8) as client, ThreadPoolExecutor(max_workers=len(names)) as pool:
                reports = dict(zip(names, pool.map(lambda name: fetch(client, name, now), names)))
            observations = []
            for product, fields in PRODUCTS.items():
                rows, error = reports[product]
                observations.extend(observation(product, field, rows[0] if rows else {}, error) for field in fields)
            future = [(when, row) for row in reports["predictions"][0]
                      if (when := timestamp(row.get("t"))) is not None and when > now]
            for tide, code in (("high", "H"), ("low", "L")):
                options = [(t, r) for t, r in future if r.get("type") == code]
                if options:
                    row = min(options, key=lambda item: item[0])[1]
                    observations.append(observation("predictions", (f"tide_next_{tide}", f"Next {tide} tide", "m", "v"), row))
            if any(row["value"] is not None for row in observations):
                self.cached = {"retrieved_at": now.isoformat(), "observations": observations}
                self.expires = monotonic() + 60
            else:
                self.cached = {"status": "unavailable", "reason": "NOAA returned no current values"}
                self.expires = monotonic() + 10
            return self.cached
