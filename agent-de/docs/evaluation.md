# Evaluation Protocol

## Current result

No evaluation has been run. `eval/run_eval.py` and `eval/results.md` do not yet exist. There is no measured self-heal success rate.

## Purpose

Measure whether injected recoverable failures lead to correct validated output within the repair budget. Separately measure whether unrecoverable failures stop safely. Deterministic evaluation tests the workflow; it does not establish live model repair quality.

## Required evaluator behavior

For every scenario:

1. Create an isolated runtime directory and fresh source/LLM fixtures.
2. Seed a previously valid dataset and schema where preservation or drift is being tested.
3. Start a monotonic timer.
4. Run the same workflow used by the application.
5. Inspect final status, validation, published values, row counts, metadata, and retries.
6. Record elapsed time and whether a repair was actually needed and performed.
7. Preserve a concise failure reason and relevant log reference.

Do not merely return the scenario's expected result from the mocked LLM. The generated or fixture code, transforms, validation, and publishing must perform real work. Identify any mocked execution boundary in the report.

## Result columns

Scenario, recoverable classification, outcome, correct final data, graph retries, transport retries, elapsed seconds, and notes.

Outcomes distinguish:

- Recovered through a generated-code repair.
- Recovered through a transport retry.
- Handled through a predeclared schema policy.
- Failed safely as expected.
- Failed unexpectedly or produced incorrect output.
- Skipped because a required capability was unavailable.

## Metrics

`Self-heal success rate = 100 × correctly recovered recoverable scenarios / all designated recoverable scenarios`

Declare recoverability before running. Include unexecuted designated recoverable cases in the denominator and mark the evaluation incomplete, so skipping difficult cases cannot inflate the headline rate. If no recoverable scenarios exist, report not applicable rather than dividing by zero.

Report transport recovery, code repair, schema handling, and safe failure separately. A safe stop on an unrecoverable case is a safety success but does not increase the self-heal numerator. A process exit code of zero is insufficient without correctness checks.

Include total scenarios, executed count, skipped count, environment/dependency versions, mock/live mode, baseline sample sizes, and sandbox backend. Keep repeatability and cold/warm cache conditions explicit.

## Output

The evaluator writes a measured Markdown table to `eval/results.md` and a short overall summary. The README links or copies measured values only after the evaluator succeeds. Keep reports from mock evaluations clearly labeled as deterministic fixtures.

Planned invocation, after implementation:

```bash
python -m eval.run_eval
```
