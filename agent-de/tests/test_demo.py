"""Demo preserves publication checks and never executes arbitrary code."""
from dataclasses import replace
import pytest
from config import Settings
from agent.graph import run_pipeline, Pipeline
from tests.failure_injection.scenarios import ScenarioAPI
from tools.demo_executor import run_trusted_transform


def test_demo_pipeline_and_code_boundary(tmp_path):
    settings = Settings(data_dir=tmp_path, demo_mode=True, backoff_seconds=0)
    result = run_pipeline('weather in Bengaluru', settings, api=ScenarioAPI())
    assert result['status'] == 'success'
    with pytest.raises(ValueError, match='trusted repository'):
        run_trusted_transform('print(123)', settings=settings, snapshots={}, plan={}, attempt_dir=tmp_path)
    with pytest.raises(ValueError, match='built-in'):
        Pipeline(replace(settings, provider='gemini'))
