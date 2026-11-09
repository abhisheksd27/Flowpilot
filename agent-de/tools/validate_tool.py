"""Pandera plus SQL data-quality gates for the canonical hourly warehouse."""
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pandera.pandas as pa
from pipeline.contracts import METRICS
from tools.schema_tool import compare_schema, inspect_schema
from tools.sql_tool import connection, identifier


def validate_data(table: str, db_path: Path | None = None, *, plan: dict | None = None,
                  expected: dict | None = None, now: datetime | None = None) -> dict:
    """Return every quality failure without dropping or fabricating measurements."""
    from config import Settings
    path = db_path or Settings.from_env().db_path
    with connection(path, read_only=True) as con:
        frame = con.execute(f"SELECT * FROM {identifier(table)}").fetchdf()
        duplicates = con.execute(f"SELECT count(*) FROM (SELECT location_id,time FROM {identifier(table)} GROUP BY location_id,time HAVING count(*)>1)").fetchone()[0]
    checks = []
    def add(name, ok, detail):
        checks.append({"check": name, "passed": bool(ok), "detail": str(detail)})
    schema = pa.DataFrameSchema({
        "time": pa.Column(pa.DateTime, nullable=False),
        "location_id": pa.Column(str, nullable=False), "city": pa.Column(str, nullable=False),
        "temperature_c": pa.Column(float, pa.Check.in_range(-60, 60), nullable=False),
        "humidity_pct": pa.Column(float, pa.Check.in_range(0, 100), nullable=False),
        "pm2_5_ug_m3": pa.Column(float, pa.Check.ge(0), nullable=False),
    }, strict=True, coerce=False)
    try:
        schema.validate(frame, lazy=True)
        add("pandera_schema", True, "Types, nulls, and value ranges passed")
    except (pa.errors.SchemaErrors, pa.errors.SchemaError) as error:
        add("pandera_schema", False, str(error)[:6000])
    nulls = frame.isna().mean().to_dict()
    add("not_empty", len(frame) > 0, f"{len(frame)} rows")
    add("null_fraction", not frame.isna().any().any(), nulls)
    add("unique_business_keys", duplicates == 0, f"{duplicates} duplicate keys")
    finite = all(pd.api.types.is_numeric_dtype(frame.get(c)) and np.isfinite(frame[c]).all() for c in METRICS if c in frame)
    add("finite_measurements", finite, "Numeric finite values required")
    now = now or datetime.now(timezone.utc)
    moment = pd.Timestamp(now).tz_convert("UTC").tz_localize(None)
    times = pd.to_datetime(frame.get("time", pd.Series(dtype="datetime64[ns]")), errors="coerce")
    latest = times.max()
    historical = bool(plan and plan.get('historical', False))
    fresh = pd.notna(latest) and latest <= moment and (historical or moment - pd.Timedelta(hours=3) <= latest)
    add("historical_time_boundary" if historical else "freshness", fresh,
        f"Latest completed hour: {latest}; checked at {moment} UTC")
    if plan:
        add("location", frame["location_id"].eq(plan["location_id"]).all() and frame["city"].eq(plan["city"]).all(), "Location matches resolved plan")
        start = pd.Timestamp(plan["window_start"])
        end = pd.Timestamp(plan["as_of"]).floor("h")
        expected_times = pd.date_range(start, end, freq="h")
        actual = pd.DatetimeIndex(times.dropna().unique())
        missing = expected_times.difference(actual)
        add("hourly_coverage", len(missing) == 0 and times.between(start, end).all(), f"{len(missing)} missing hours; expected {len(expected_times)}")
    actual_schema = inspect_schema(table, path)["columns"]
    drift = compare_schema(expected, actual_schema) if expected else {"detected": False}
    add("target_schema", not drift["detected"], drift)
    return {"valid": all(c["passed"] for c in checks), "checks": checks, "rows": len(frame),
            "null_percent": {k: round(v * 100, 3) for k, v in nulls.items()},
            "schema": actual_schema, "schema_drift": drift}
