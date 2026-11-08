"""Run deterministic failure cases and write measured, explicitly mocked results."""
from pathlib import Path
import tempfile
import time
from tests.failure_injection.scenarios import SCENARIOS, run_scenario


def main() -> int:
    rows, recovered = [], 0
    for scenario in SCENARIOS:
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="flowpilot-eval-") as directory:
            result = run_scenario(scenario, Path(directory))
        success = result["status"] == "success" and result["correct_data"]
        recovered += int(success)
        rows.append(f"| {scenario} | {'Recovered' if success else 'Failed'} | {result['retry_count']} | {time.monotonic()-start:.2f} |")
    text = "\n".join(["# Failure-injection evaluation", "", "Mode: deterministic HTTP/model fixtures; real transformations, Pandera checks, DuckDB transactions, and LangGraph routing. The fixture executor is not evidence of OS isolation or live LLM quality.", "", "| Scenario | Outcome | Graph retries | Seconds |", "| --- | --- | ---: | ---: |", *rows, "", f"Self-heal success rate: **{100*recovered/len(SCENARIOS):.1f}%** ({recovered}/{len(SCENARIOS)} recoverable scenarios).", "", "Persistent-failure preservation and sandbox boundaries are covered separately by pytest.", ""])
    target = Path(__file__).with_name("results.md")
    target.write_text(text)
    print(text)
    return int(recovered != len(SCENARIOS))


if __name__ == "__main__":
    raise SystemExit(main())
