"""Offline graph contracts and transactional preservation."""
from dataclasses import replace
import json
from agent.graph import run_pipeline
from config import Settings
from pipeline.warehouse import run_lock
from tests.failure_injection.scenarios import ScenarioAPI, fixture_executor
from tools.sql_tool import connection
import pytest


def test_real_transform_and_idempotency(tmp_path):
    settings = Settings(data_dir=tmp_path, backoff_seconds=0)
    events = []
    first = run_pipeline("weather for Bengaluru", settings, api=ScenarioAPI(), executor=fixture_executor, on_event=events.append)
    second = run_pipeline("weather for Bengaluru", settings, api=ScenarioAPI(), executor=fixture_executor)
    assert first["status"] == second["status"] == "success", first["errors"]
    assert second["published"]["net_new_rows"] == 0
    assert first["published"]["warehouse_rows"] == second["published"]["warehouse_rows"]
    assert "Real Pipeline Report" in first["final_report"]
    assert any(x["node"] == "sandbox" and x["status"] == "running" for x in events)
    assert events[-1]["outcome"] == "success"
    assert list((tmp_path / "bronze").rglob("*.json"))
    assert json.loads((tmp_path / "latest.json").read_text())["status"] == "success"


def test_lock_prevents_concurrent_runs(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with run_lock(settings):
        with pytest.raises(RuntimeError, match="Another pipeline"):
            with run_lock(settings):
                pass


def test_unrecognized_request_reports_failure(tmp_path):
    state = run_pipeline("buy stocks", Settings(data_dir=tmp_path), api=ScenarioAPI(), executor=fixture_executor)
    assert state["status"] == "failed"
    assert not state["published"]
    assert "supports weather" in state["final_report"]
