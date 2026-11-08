"""Nine recovery scenarios plus persistent faults that must fail safely."""
import pytest
from tests.failure_injection.scenarios import SCENARIOS, run_scenario


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_recovery(scenario, tmp_path):
    result = run_scenario(scenario, tmp_path)
    assert result["status"] == "success", result["errors"]
    assert result["correct_data"]
    assert 1 <= result["retry_count"] <= 3
    assert len({x["fingerprint"] for x in result["previous_fixes"]}) == len(result["previous_fixes"])


@pytest.mark.parametrize("scenario", ("removed_field", "null_spike", "out_of_range", "api_timeout", "malformed_json"))
def test_persistent_failure_keeps_good_data(scenario, tmp_path):
    result = run_scenario(scenario, tmp_path, persistent=True)
    assert result["status"] == "failed", result["errors"]
    assert result["correct_data"]
    assert not result["published"]
    assert result["retry_count"] <= 3
