"""Canonical dataset definitions, supported request parsing, and code templates."""
import json
import re
from datetime import datetime, timezone

WEATHER = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
SCHEMA = {"time": "TIMESTAMP_NS", "location_id": "VARCHAR", "city": "VARCHAR",
          "temperature_c": "DOUBLE", "humidity_pct": "DOUBLE", "pm2_5_ug_m3": "DOUBLE"}
METRICS = ["temperature_c", "humidity_pct", "pm2_5_ug_m3"]


def default_plan(request: str) -> dict:
    """Parse the supported environmental request; disclose a fallback location."""
    if not request.strip():
        raise ValueError("Enter a request")
    if not re.search(r"weather|\btemp\b|temperature|humidity|air quality|pollution|pm2", request, re.I):
        raise ValueError("This project supports weather and air-quality requests only")
    match = re.search(r"(?:for|in)\s+([\w ,'-]+?)(?=\s+and\b|[.!?]|$)", request, re.I)
    city = match.group(1).strip() if match else "Bengaluru"
    city = re.sub(r"\s+(daily|hourly)$", "", city, flags=re.I)
    return {"source": "Open-Meteo", "city": city, "endpoints": [WEATHER, AIR],
            "parameters": {"past_days": 5, "forecast_days": 1, "timezone": "UTC"},
            "target_table": "silver_environment", "schema": SCHEMA,
            "transformations": ["Join hourly timestamps", "Retain completed UTC hours",
                                "Publish hourly records and daily local-date aggregates"],
            "validation_rules": {"null_fraction": 0, "duplicates": 0, "freshness_hours": 3,
                                 "temperature_c": [-60, 60], "humidity_pct": [0, 100]},
            "schedule_suggestion": "Daily at 08:00 Asia/Kolkata",
            "assumptions": ["Weather and air quality are modeled estimates, not station observations.",
                            "Includes both weather and air quality; daily reporting retains hourly detail."]
                           + ([] if match else ["No location specified; using Bengaluru."])}


def validate_plan(plan: dict) -> dict:
    """Keep model proposals within the implemented warehouse contract."""
    required = {"source", "city", "endpoints", "parameters", "target_table", "schema",
                "transformations", "validation_rules", "schedule_suggestion"}
    if not isinstance(plan, dict) or required - plan.keys():
        raise ValueError("Plan is missing required fields")
    if set(plan["endpoints"]) != {WEATHER, AIR} or plan["target_table"] != "silver_environment":
        raise ValueError("Unsupported endpoint or target table")
    if plan["schema"] != SCHEMA:
        raise ValueError("Plan must preserve the canonical environmental schema")
    if not isinstance(plan["city"], str) or not 1 <= len(plan["city"]) <= 100:
        raise ValueError("Invalid city name")
    # Quality constraints are host policy, never relaxed by model output.
    contract = default_plan("weather for " + plan["city"])
    contract["assumptions"] = list(contract["assumptions"])
    return contract


def transform_code(*, numeric: bool = False, deduplicate: bool = False,
                   aliases: dict | None = None) -> str:
    """Return a full idempotent staging pipeline; helpers are brokered by the worker."""
    aliases = aliases or {}
    numeric_code = "\n".join(f'frame[{name!r}] = pd.to_numeric(frame[{name!r}], errors="raise").astype(float)'
                             for name in METRICS) if numeric else ""
    dedup_code = '''
for part in (weather, air):
    for column in part.columns:
        if column != "time" and (part.groupby("time")[column].nunique(dropna=False) > 1).any():
            raise ValueError("Conflicting duplicate source measurements")
weather = weather.drop_duplicates(subset=["time"])
air = air.drop_duplicates(subset=["time"])
''' if deduplicate else ""
    return f'''import pandas as pd
# call_api serves only the approved immutable response snapshots.
weather = pd.DataFrame(call_api("weather")["hourly"])
air = pd.DataFrame(call_api("air")["hourly"])
weather = weather.rename(columns={aliases!r})
weather = weather[["time", "temperature_2m", "relative_humidity_2m"]]
air = air[["time", "pm2_5"]]
weather["time"] = pd.to_datetime(weather["time"], errors="raise")
air["time"] = pd.to_datetime(air["time"], errors="raise")
{dedup_code}
frame = weather.merge(air, on="time", how="outer")
frame = frame.rename(columns={{"temperature_2m": "temperature_c", "relative_humidity_2m": "humidity_pct", "pm2_5": "pm2_5_ug_m3"}})
frame = frame[frame["time"].between(pd.Timestamp(plan["window_start"]), pd.Timestamp(plan["as_of"]))]
frame["location_id"] = str(plan["location_id"])
frame["city"] = plan["city"]
for column in ["temperature_c", "humidity_pct", "pm2_5_ug_m3"]:
    if pd.api.types.is_numeric_dtype(frame[column]):
        frame[column] = frame[column].astype(float)
{numeric_code}
# The helper replaces only this attempt's own staging table.
load_frame(frame[["time", "location_id", "city", "temperature_c", "humidity_pct", "pm2_5_ug_m3"]])
print("Staged", len(frame), "hourly records")
'''


def reference_frame(snapshots: dict, plan: dict, options: dict):
    """Reconcile every generated measurement against trusted source transformations."""
    import pandas as pd
    weather = pd.DataFrame(snapshots["weather"]["hourly"]).rename(columns=options["aliases"])
    air = pd.DataFrame(snapshots["air"]["hourly"])
    weather = weather[["time", "temperature_2m", "relative_humidity_2m"]].copy()
    air = air[["time", "pm2_5"]].copy()
    for part in (weather, air):
        part["time"] = pd.to_datetime(part["time"], errors="raise")
        if options["deduplicate"]:
            for column in part.columns:
                if column != "time" and (part.groupby("time")[column].nunique(dropna=False) > 1).any():
                    raise ValueError("Conflicting duplicate source measurements")
            part.drop_duplicates(subset=["time"], inplace=True)
    frame = weather.merge(air, on="time", how="outer").rename(columns={
        "temperature_2m": "temperature_c", "relative_humidity_2m": "humidity_pct", "pm2_5": "pm2_5_ug_m3"})
    frame = frame[frame["time"].between(pd.Timestamp(plan["window_start"]), pd.Timestamp(plan["as_of"]))].copy()
    frame["location_id"], frame["city"] = str(plan["location_id"]), plan["city"]
    for column in METRICS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    return frame[list(SCHEMA)].sort_values(["location_id", "time"]).reset_index(drop=True)
