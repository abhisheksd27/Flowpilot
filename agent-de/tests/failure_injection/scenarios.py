"""Deterministic, genuinely executed transformations with controlled source failures."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
from config import Settings
from agent.graph import run_pipeline
from agent.llm import BuiltinClient
from pipeline.contracts import GEO, WEATHER, transform_code
from tools.sql_tool import connection

SCENARIOS = ("renamed_field", "removed_field", "new_field", "type_change", "null_spike",
             "duplicate_rows", "api_timeout", "malformed_json", "out_of_range")


def healthy_snapshots() -> dict:
    """Five historical UTC days and today's hours, with proper source units."""
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    start = now.normalize() - pd.Timedelta(days=5)
    times = pd.date_range(start, now.normalize() + pd.Timedelta(hours=23), freq="h")
    n = len(times)
    return {"weather": {"hourly": {"time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
                    "temperature_2m": [24.0 + (i % 12) / 10 for i in range(n)],
                    "relative_humidity_2m": [60.0 + i % 8 for i in range(n)]},
                    "hourly_units": {"temperature_2m": "°C", "relative_humidity_2m": "%"}},
            "air": {"hourly": {"time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
                    "pm2_5": [18.0 + i % 5 for i in range(n)]}, "hourly_units": {"pm2_5": "μg/m³"}}}


class ScenarioAPI:
    """Faults occur on the first attempt; schema/type faults persist until repaired."""
    def __init__(self, scenario="healthy", persistent=False):
        self.scenario, self.persistent = scenario, persistent
        self.metrics = {"requests": 0, "cache_hits": 0, "retries": 0}
        self.weather_calls = 0

    def call_api(self, url, params, *, refresh=False):
        import requests
        self.metrics["requests"] += 1
        if url == GEO:
            return {"results": [{"id": 1277333, "name": "Bengaluru", "latitude": 12.97,
                                "longitude": 77.59, "timezone": "Asia/Kolkata", "country": "India"}]}
        weather = url == WEATHER
        if weather:
            self.weather_calls += 1
        payload = deepcopy(healthy_snapshots()["weather" if weather else "air"])
        fault = self.scenario
        if weather:
            transient = self.weather_calls == 1 or self.persistent
            fields = payload["hourly"]
            if fault == "api_timeout" and transient:
                raise requests.Timeout("Injected source timeout")
            if fault == "malformed_json" and transient:
                raise ValueError("Injected malformed JSON response")
            if fault == "renamed_field":
                fields["temperature"] = fields.pop("temperature_2m")
                payload["hourly_units"]["temperature"] = payload["hourly_units"].pop("temperature_2m")
            if fault == "removed_field" and transient:
                fields.pop("relative_humidity_2m")
            if fault == "new_field":
                fields["wind_speed_10m"] = [4.0] * len(fields["time"])
            if fault == "type_change":
                fields["temperature_2m"] = [str(x) for x in fields["temperature_2m"]]
            if fault == "null_spike" and transient:
                fields["temperature_2m"][:24] = [None] * 24
            if fault == "out_of_range" and transient:
                fields["temperature_2m"][0] = 999.0
            if fault == "duplicate_rows":
                for values in fields.values():
                    values.append(values[0])
        return payload


def fixture_executor(code, *, settings, snapshots, plan, attempt_dir):
    """Execute ONLY known fixture templates; never a production sandbox fallback."""
    import itertools
    allowed = {transform_code(numeric=n, deduplicate=d, aliases=a)
               for n, d, a in itertools.product((False, True), (False, True), ({}, {"temperature": "temperature_2m"}))}
    assert code in allowed, "Offline executor accepts only repository-owned fixture programs"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    path = attempt_dir / "staging.duckdb"
    def load_frame(frame):
        with connection(path) as con:
            con.register("incoming", frame)
            con.execute("CREATE OR REPLACE TABLE staged AS SELECT * FROM incoming")
    try:
        exec(code, {"call_api": lambda source: deepcopy(snapshots[source]), "load_frame": load_frame, "plan": plan})
        return {"success": True, "db_path": str(path), "stdout": "Fixture execution", "backend": "trusted-fixture"}
    except Exception as error:
        return {"success": False, "error": str(error), "backend": "trusted-fixture"}


def run_scenario(name: str, data_dir: Path, *, persistent: bool = False) -> dict:
    """Seed a healthy baseline, then exercise the same graph with injected faults."""
    settings = Settings(data_dir=data_dir, backoff_seconds=0)
    request = "Track daily weather and air quality for Bengaluru and flag anomalies."
    baseline = run_pipeline(request, settings, api=ScenarioAPI(), executor=fixture_executor)
    if baseline["status"] != "success":
        raise AssertionError(baseline["errors"])
    result = run_pipeline(request, settings, api=ScenarioAPI(name, persistent), executor=fixture_executor)
    with connection(settings.db_path, read_only=True) as con:
        bad = con.execute("SELECT count(*) FROM silver_environment WHERE temperature_c IS NULL OR temperature_c NOT BETWEEN -60 AND 60").fetchone()[0]
        duplicates = con.execute("SELECT count(*)-count(DISTINCT (location_id,time)) FROM silver_environment").fetchone()[0]
    result["correct_data"] = bad == 0 and duplicates == 0
    result["baseline_rows"] = baseline["published"]["warehouse_rows"]
    return result
