"""Bronze lineage, transactional silver upserts, and daily gold aggregates."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import pandas as pd
from config import Settings
from pipeline.contracts import METRICS
from tools.sql_tool import connection


@contextmanager
def run_lock(settings: Settings):
    """Serialize CLI, UI, and scheduler writers across processes."""
    settings.prepare()
    with (settings.data_dir / "pipeline.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another pipeline run is active; try again after it finishes") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def initialize(settings: Settings) -> None:
    """Create host-owned metadata without claiming existing data tables."""
    settings.prepare()
    with connection(settings.db_path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS _agent_tables (table_name VARCHAR PRIMARY KEY, created_at TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS _agent_schemas (dataset VARCHAR PRIMARY KEY, version INTEGER, schema_json VARCHAR, accepted_at TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS _agent_schema_events (run_id VARCHAR, dataset VARCHAR, diff_json VARCHAR, decision VARCHAR, event_at TIMESTAMP)")
        con.execute("CREATE TABLE IF NOT EXISTS _agent_runs (run_id VARCHAR PRIMARY KEY, status VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, rows_published INTEGER, report_path VARCHAR)")


def publish(settings: Settings, frame: pd.DataFrame, plan: dict, run_id: str,
            schemas: dict[str, dict], drift: dict) -> dict:
    """Publish hourly and daily tables atomically, retaining history and lineage."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    incoming = frame.copy()
    incoming["run_id"] = run_id
    incoming["ingested_at"] = now
    with connection(settings.db_path) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            for table in ("silver_environment", "gold_daily_environment"):
                exists = con.execute("SELECT 1 FROM information_schema.tables WHERE table_name=?", [table]).fetchone()
                owned = con.execute("SELECT 1 FROM _agent_tables WHERE table_name=?", [table]).fetchone()
                if exists and not owned:
                    raise PermissionError(f"Refusing to replace non-agent table: {table}")
            con.register("incoming", incoming)
            con.execute("CREATE TABLE IF NOT EXISTS silver_environment AS SELECT * FROM incoming LIMIT 0")
            old_count = con.execute("SELECT count(*) FROM silver_environment").fetchone()[0]
            con.execute("DELETE FROM silver_environment USING incoming WHERE silver_environment.location_id=incoming.location_id AND silver_environment.time=incoming.time")
            con.execute("INSERT INTO silver_environment BY NAME SELECT * FROM incoming")
            full = con.execute("SELECT * FROM silver_environment WHERE location_id=? ORDER BY time", [plan["location_id"]]).fetchdf()
            local = pd.to_datetime(full["time"], utc=True).dt.tz_convert(plan["timezone"])
            full["date"] = local.dt.date
            daily = full.groupby(["location_id", "city", "date"], as_index=False).agg(
                temperature_c=("temperature_c", "mean"), humidity_pct=("humidity_pct", "mean"),
                pm2_5_ug_m3=("pm2_5_ug_m3", "mean"), samples=("time", "count"))
            daily["timezone"] = plan["timezone"]
            today = pd.Timestamp.now(tz=plan["timezone"]).date()
            daily["complete_day"] = (daily["date"] < today) & (daily["samples"] >= 24)
            daily["run_id"] = run_id
            daily["ingested_at"] = now
            con.register("daily", daily)
            con.execute("CREATE TABLE IF NOT EXISTS gold_daily_environment AS SELECT * FROM daily LIMIT 0")
            con.execute("DELETE FROM gold_daily_environment WHERE location_id=?", [plan["location_id"]])
            con.execute("INSERT INTO gold_daily_environment BY NAME SELECT * FROM daily")
            for table in ("silver_environment", "gold_daily_environment"):
                con.execute("INSERT INTO _agent_tables VALUES (?, ?) ON CONFLICT DO NOTHING", [table, now])
            for dataset, schema in schemas.items():
                old = con.execute("SELECT version, schema_json FROM _agent_schemas WHERE dataset=?", [dataset]).fetchone()
                encoded = json.dumps(schema, sort_keys=True)
                version = (old[0] + (old[1] != encoded)) if old else 1
                con.execute("INSERT INTO _agent_schemas VALUES (?, ?, ?, ?) ON CONFLICT(dataset) DO UPDATE SET version=excluded.version, schema_json=excluded.schema_json, accepted_at=excluded.accepted_at", [dataset, version, encoded, now])
            if drift.get("detected"):
                con.execute("INSERT INTO _agent_schema_events VALUES (?, ?, ?, ?, ?)",
                            [run_id, plan["location_id"], json.dumps(drift), "accepted after repair and validation; canonical output retained", now])
            count = con.execute("SELECT count(*) FROM silver_environment").fetchone()[0]
            con.execute("COMMIT")
            return {"hourly_rows": len(incoming), "daily_rows": len(daily), "warehouse_rows": count,
                    "net_new_rows": count - old_count, "location_id": plan["location_id"]}
        except Exception:
            con.execute("ROLLBACK")
            raise


def preview(settings: Settings, table: str = "gold_daily_environment", limit: int = 1000) -> pd.DataFrame:
    """Return a bounded trusted dashboard preview."""
    if table not in {"gold_daily_environment", "silver_environment", "_agent_runs", "_agent_schema_events"}:
        raise ValueError("Unsupported preview table")
    if not settings.db_path.exists():
        return pd.DataFrame()
    with connection(settings.db_path, read_only=True) as con:
        try:
            order = "time DESC" if table == "silver_environment" else (
                "date DESC" if table == "gold_daily_environment" else "1 DESC")
            return con.execute(f'SELECT * FROM "{table}" ORDER BY {order} LIMIT ?', [min(limit, 5000)]).fetchdf()
        except Exception:
            return pd.DataFrame()
