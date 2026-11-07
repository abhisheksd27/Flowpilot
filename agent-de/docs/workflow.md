# Workflow and State

This is the planned LangGraph contract. Implementation belongs to the developer.

## State

| Field | Purpose |
| --- | --- |
| `user_request` | Original user request |
| `plan` | Validated JSON specification |
| `code` | Current full generated program |
| `execution_result` | Status, stdout, stderr, staging path, and duration |
| `validation_result` | Quality checks, source completeness, and schema differences |
| `errors` | Ordered error history |
| `retry_count` | Repair retries consumed by the execution/validation cycle |
| `step_history` | Observable action summaries and results |
| `final_report` | Final Markdown report |
| `run_id` | Unique identifier for logs and artifacts |
| `previous_fixes` | Diagnoses, normalized code hashes, and repair decisions |
| `step_retries` | Retry counts for other steps, such as planning |
| `source_snapshots` | Approved input responses or host-owned references |
| `anomalies` | Statistical results and sample-size information |
| `publish_result` | Whether data was committed and how many records changed |

The first eight fields come from the project requirements. The remaining fields support the planned implementation. Do not put credentials into state.

## Node contracts

| Node | Input | Successful output | Failure route |
| --- | --- | --- | --- |
| `plan` | Request and catalog | Validated plan and assumptions | Retry planning, then report |
| `generate_code` | Plan and execution contract | Policy-checked Python | Retry generation, then report |
| `execute` | Code, plan, approved sources | Staged table and execution result | Diagnose and fix |
| `validate` | Staged data and expected schemas | Passed checks and committed publish result | Diagnose and fix, or report policy failure |
| `diagnose_and_fix` | Code, errors, checks, schema diff, prior fixes | Distinct permitted corrected program | Stop after budget or unrecoverable condition |
| `anomaly_detect` | Validated warehouse data | Flags, thresholds, and sample counts | Bounded retry, then report partial outcome |
| `report` | Entire observable run state | Markdown report | Local fallback report if optional formatting fails |

## Planning

The plan includes `source`, `endpoints`, `parameters`, `target_table`, `schema`, `transformations`, `validation_rules`, and `schedule_suggestion`.

Also record location resolution, business key, timezone, date window, frequency, units, and assumptions. Reject unsupported source requests rather than inventing endpoints.

## Generation and execution

Generate a complete program, then validate its syntax and permissions. Fetch the approved API requests through the host broker. Execute the program against those responses and a staging database with a 30-second subprocess limit. Capture bounded output and clean up the entire child process group on timeout.

Validate incoming field structure before transformation so aggregation cannot hide removed fields or missing measurements.

## Validation and publishing

Check required columns, types, null percentages, duplicate business keys, value ranges, empty output, timestamp semantics, source coverage, and source/output schema drift. Preserve detailed failures for the fix prompt.

When checks pass, confirm table ownership and publish in a single transaction. Apply an approved migration when needed, upsert the intended records, update accepted metadata, and commit. Roll back on failure. Retain the previous valid dataset when validation or publishing fails.

## Repair rules

Provide failing code, error messages, validation failures, schema differences, and previous fixes to the LLM. Require corrected full code and a one-line diagnosis. Schema acceptance must be explicit and recorded.

Normalize code before hashing it to reject whitespace-only repetitions. Track accepted repair decisions as well as code hashes. A repeated repair proposal consumes a retry but is not executed again. Stop immediately on a security violation or an unrecoverable condition.

Do not fabricate observations, remove required checks, silently drop bad records, or reinterpret missing required fields as success. Any permitted exclusion or imputation must come from the plan and be disclosed in the report.

## Retry accounting

- Initial attempt plus at most three retries per step.
- One shared repair counter for execution and validation; changing the failure type does not reset it.
- Planning and generation maintain their own counters and cannot proceed with invalid outputs.
- Transport retries are separately bounded by the API/LLM clients and logged separately from graph retries.
- The same HTTP operation can therefore be attempted more than four times across several graph attempts. Report both layers and apply a total run deadline before supporting unattended operation.
- Security violations and missing sandbox isolation are terminal, not repairable model errors.

## Prompt response formats

The required general system prompt asks for valid JSON. Planning and repair return JSON. Code generation is the explicit exception: use a code-specific system instruction and `json_mode=False` to request only runnable Python. Do not issue contradictory JSON and raw-code requirements in the same generation call.

The repair JSON contains full corrected code and a diagnosis; the host extracts the code before execution. Keep all prompt text and the catalog in `agent/prompts.py`.

## Anomalies and reports

Calculate z-score and IQR flags on validated numeric measurements. Specify the baseline, sample count, standard-deviation convention, and insufficient-data behavior. A recommended initial contract is population standard deviation, at least eight non-null samples, and an explicit insufficient-data result below that threshold. Constant series produce no z-score flags. A zero IQR should be reported as a degenerate baseline rather than silently treated as a useful detector.

The report includes request, assumptions, source attribution, location, time window, timezone, row counts, quality checks, changes, repairs, anomaly limitations, usage statistics, and log location. A failure report explains the last failure, retry count, and whether any data was published.

## UI flow

Request text and provider selection → Run → streamed node log → result tabs.

Tabs: Plan, Generated Code, Validation Results, Anomalies with a chart, Final Report, and Table Preview. Download the Markdown report. Persist the completed run in UI session state so tab changes do not rerun ingestion. Disable conflicting writes while a run is active.
