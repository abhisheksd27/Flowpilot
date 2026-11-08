"""Actual OS-boundary integration tests, enabled explicitly on a supported host."""
import os
import pytest
from config import Settings
from tools.python_sandbox import run_python

pytestmark = [pytest.mark.sandbox, pytest.mark.skipif(os.getenv("FLOWPILOT_SANDBOX_TESTS") != "1", reason="Set FLOWPILOT_SANDBOX_TESTS=1 for OS isolation tests")]


def test_staging_and_outside_reads(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    good = run_python('import pandas as pd\nload_frame(pd.DataFrame({"x":[1.0]}))', settings=settings)
    assert good["success"], good
    secret = tmp_path / "outside.csv"
    secret.write_text("x\n123\n")
    bad = run_python(f'import pandas as pd\nload_frame(pd.read_csv({str(secret)!r}))', settings=settings)
    assert not bad["success"] and "PermissionError" in bad["error"]
    job = settings.data_dir / "runs" / "symlink"
    job.mkdir()
    (job / "escape.csv").symlink_to(secret)
    escape = run_python('import pandas as pd\nload_frame(pd.read_csv("escape.csv"))', settings=settings, attempt_dir=job)
    assert not escape["success"] and "PermissionError" in escape["error"]


def test_outside_writes_and_network(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    outside = tmp_path / "outside.csv"
    result = run_python(f'import pandas as pd\npd.DataFrame({{"x":[1]}}).to_csv({str(outside)!r})', settings=settings)
    assert not result["success"] and "PermissionError" in result["error"] and not outside.exists()
    result = run_python('import requests\nrequests.get("https://example.com")', settings=settings)
    assert not result["success"] and "PermissionError" in result["error"]


def test_timeout_and_output_cap(tmp_path):
    result = run_python('while True:\n    pass', settings=Settings(data_dir=tmp_path, python_timeout=2))
    assert result["timed_out"]
    result = run_python('print("x" * 50000)', settings=Settings(data_dir=tmp_path))
    assert not result["success"] and "32 KB" in result["error"]
