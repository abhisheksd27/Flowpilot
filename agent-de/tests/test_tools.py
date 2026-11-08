"""Offline tool contracts: HTTP, providers, SQL policy, schemas, statistics, and scheduling."""
from datetime import datetime, timezone
from unittest.mock import Mock
import duckdb
import pandas as pd
import pytest
import requests
from config import Settings
from agent.llm import GeminiClient, GroqClient, OllamaClient
from tools.api_tool import APITool, check_url
from tools.cache import DiskCache, digest
from tools.sql_tool import connection, run_sql
from tools.schema_tool import compare_schema, inspect_schema
from tools.anomaly_tool import detect_anomalies
from tools.python_sandbox import validate_code, code_fingerprint, SandboxPolicyError
from pipeline.scheduler import next_run
from pipeline.warehouse import initialize
from pipeline.contracts import WEATHER


class Response:
    def __init__(self, body=b'{"hourly": {}}', status=200):
        self.body, self.status_code = body, status
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("fixture HTTP error", response=self)
    def iter_content(self, size): yield self.body


@pytest.mark.parametrize("url", ["http://api.open-meteo.com/v1/forecast", "https://api.open-meteo.com.evil.test/v1/forecast", "https://user@api.open-meteo.com/v1/forecast", "https://api.open-meteo.com/v1/forecast?x=1", "https://api.open-meteo.com/other"])
def test_domain_policy(url):
    with pytest.raises(ValueError): check_url(url)


def test_api_retry_cache_and_malformed_json(tmp_path):
    session = Mock()
    session.get.side_effect = [requests.Timeout("fixture"), Response(b'bad json'), Response()]
    api = APITool(Settings(data_dir=tmp_path, backoff_seconds=0), session)
    assert api.call_api(WEATHER, {}) == {"hourly": {}}
    assert api.metrics["retries"] == 2
    assert api.call_api(WEATHER, {}) == {"hourly": {}}
    assert api.metrics["cache_hits"] == 1 and session.get.call_count == 3
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("status", [301, 400, 401])
def test_api_permanent_errors(tmp_path, status):
    session = Mock()
    session.get.return_value = Response(status=status)
    with pytest.raises((PermissionError, requests.HTTPError)):
        APITool(Settings(data_dir=tmp_path, backoff_seconds=0), session).call_api(WEATHER, {})
    assert session.get.call_count == 1


def test_api_size_cap(tmp_path):
    session = Mock()
    session.get.return_value = Response(b'x' * 5_000_001)
    with pytest.raises(PermissionError):
        APITool(Settings(data_dir=tmp_path), session).call_api(WEATHER, {})


def test_cache_corruption_and_expiry(tmp_path):
    cache = DiskCache(tmp_path, 100)
    key = digest({"b": 2, "a": 1})
    assert key == digest({"a": 1, "b": 2})
    cache.put(key, {"ok": True})
    assert cache.get(key) == {"ok": True}
    assert DiskCache(tmp_path, 0).get(key) is None
    (tmp_path / f"{key}.json").write_text('[]')
    assert cache.get(key) is None


@pytest.mark.parametrize("adapter", [GeminiClient, GroqClient, OllamaClient])
def test_provider_interface_usage_and_cache(adapter, tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, gemini_key="fixture", groq_key="fixture", backoff_seconds=0)
    body = ({"message": {"content": '{"ok":true}'}, "prompt_eval_count": 4, "eval_count": 2}
            if adapter is OllamaClient else
            {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}],
             "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2}}
            if adapter is GeminiClient else
            {"choices": [{"message": {"content": '{"ok":true}'}}],
             "usage": {"prompt_tokens": 4, "completion_tokens": 2}})
    response = Mock(status_code=200)
    response.json.return_value = body
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    client = adapter(settings)
    assert client.complete("system", "prompt") == '{"ok":true}'
    assert client.complete("system", "prompt") == '{"ok":true}'
    assert post.call_count == 1 and client.metrics["input_tokens"] == 4
    assert client.metrics["cache_hits"] == 1


def test_provider_backoff_and_missing_key(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, groq_key="fixture", backoff_seconds=0)
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": '{}'}}]}
    monkeypatch.setattr(requests, "post", Mock(side_effect=[requests.Timeout(), response]))
    assert GroqClient(settings).complete("s", "p") == '{}'
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiClient(settings).complete("s", "p")


def test_gemini_uses_native_key_header_and_json_mode(tmp_path):
    settings = Settings(data_dir=tmp_path, gemini_key="AQ_fixture")
    url, headers, body = GeminiClient(settings).request(
        [{"role": "system", "content": "system"}, {"role": "user", "content": "prompt"}], True)
    assert url.endswith("/gemini-3.8-flash:generateContent")
    assert headers == {"x-goog-api-key": "AQ_fixture"}
    assert body["systemInstruction"]["parts"][0]["text"] == "system"
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_sql_ownership_and_external_access(tmp_path):
    settings = Settings(data_dir=tmp_path)
    initialize(settings)
    with connection(settings.db_path) as con:
        con.execute("CREATE TABLE personal(x INTEGER)")
        con.execute("CREATE TABLE managed(x INTEGER)")
        con.execute("INSERT INTO managed VALUES (1),(2)")
        con.execute("INSERT INTO _agent_tables VALUES ('managed', current_timestamp)")
    assert run_sql("SELECT count(*) FROM managed", settings.db_path)["rows"] == [(2,)]
    for query in ("DELETE FROM personal WHERE x=1", "DROP TABLE personal", "DELETE FROM managed", "ALTER TABLE managed ADD y INTEGER", "ATTACH 'other.db' AS other", "SET enable_external_access=true"):
        with pytest.raises((PermissionError, ValueError)):
            run_sql(query, settings.db_path)
    with pytest.raises(PermissionError):
        run_sql("DELETE FROM managed WHERE x=1", settings.db_path, read_only=True)
    run_sql("DELETE FROM managed WHERE x=1", settings.db_path)
    assert run_sql("SELECT * FROM managed", settings.db_path)["rows"] == [(2,)]
    with pytest.raises(ValueError):
        run_sql("SELECT 1; DELETE FROM managed WHERE x=2", settings.db_path)
    with pytest.raises(duckdb.Error):
        run_sql("SELECT * FROM read_csv_auto('/etc/passwd')", settings.db_path)


def test_schema_and_inspection(tmp_path):
    path = tmp_path / "test.duckdb"
    with connection(path) as con: con.execute("CREATE TABLE sample AS SELECT 1 AS value")
    assert inspect_schema("sample", path)["row_count"] == 1
    diff = compare_schema({"old": "number", "x": "number"}, {"new": "number", "x": "string"})
    assert diff["detected"] and diff["possible_renames"] == [{"from": "old", "to": "new"}]
    assert diff["type_changes"]["x"]["after"] == "string"


def test_anomalies(tmp_path):
    path = tmp_path / "test.duckdb"
    with connection(path) as con:
        frame = pd.DataFrame({"value": [10.0 + i % 3 for i in range(30)] + [90.0]})
        con.register("frame", frame)
        con.execute("CREATE TABLE measurements AS SELECT * FROM frame")
        con.execute("CREATE TABLE small AS SELECT 1.0 AS value")
    assert detect_anomalies("measurements", "value", path)["count"] == 1
    assert detect_anomalies("small", "value", path)["status"] == "insufficient_data"


@pytest.mark.parametrize("code", ["import os", "from pathlib import Path", "open('x')", "x.__class__", "eval('1')", "import pandas.io.common"])
def test_code_policy(code):
    with pytest.raises(SandboxPolicyError): validate_code(code)


def test_code_fingerprint():
    assert code_fingerprint("x=1") == code_fingerprint("# same\nx = 1\n")


def test_daily_schedule(tmp_path):
    settings = Settings(data_dir=tmp_path, schedule_frequency="daily")
    assert next_run(settings, datetime(2026, 11, 8, 1, tzinfo=timezone.utc)).isoformat() == "2026-11-08T02:30:00+00:00"
    assert next_run(settings, datetime(2026, 11, 8, 3, tzinfo=timezone.utc)).isoformat() == "2026-11-09T02:30:00+00:00"


def test_hourly_schedule(tmp_path):
    settings = Settings(data_dir=tmp_path, schedule_frequency="hourly")
    # 07:35 IST -> 08:00 IST, then strictly next hour at a boundary.
    assert next_run(settings, datetime(2026, 11, 8, 2, 5, tzinfo=timezone.utc)).isoformat() == "2026-11-08T02:30:00+00:00"
    assert next_run(settings, datetime(2026, 11, 8, 2, 30, tzinfo=timezone.utc)).isoformat() == "2026-11-08T03:30:00+00:00"
    assert next_run(settings, datetime(2026, 11, 8, 18, 45, tzinfo=timezone.utc)).isoformat() == "2026-11-08T19:30:00+00:00"


def test_invalid_frequency(tmp_path):
    with pytest.raises(ValueError, match="SCHEDULE_FREQUENCY"):
        Settings(data_dir=tmp_path, schedule_frequency="weekly")
