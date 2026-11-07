# Testing Strategy

## Status

Test package directories exist, but test cases are not implemented. This document defines the required evidence. It does not report passing tests.

## Test layers

| Layer | Scope | Dependencies |
| --- | --- | --- |
| Unit | Individual tools and provider request/response formats | Temporary paths and HTTP/client fakes |
| Graph integration | Node routing, retries, staging, publishing, reports | Deterministic LLM and source fixtures |
| Sandbox integration | Isolation, timeout, resource and import policies | Actual supported isolation backend |
| Live smoke | Real source and selected provider compatibility | Explicitly enabled network and credentials |

Default CI must not require API keys or internet access. Mock network calls and use a scripted LLM response sequence. The graph should receive injected clients and tools. Use temporary databases and caches so tests cannot modify a user's warehouse.

Do not use mocked execution as evidence that the real sandbox is safe. Report missing sandbox backend tests as skipped/unverified and require actual backend verification before calling a release complete.

## Unit checks

- Configuration: environment precedence, project-relative paths, invalid numeric values, missing keys, and provider selection.
- API: exact host/path restrictions, credentials/redirect rejection, parameter validation, transient retries, permanent errors, cache hits/expiry, and malformed JSON.
- Cache: stable hashing, expired entries, malformed envelopes, and replacement without partial JSON reads.
- LLM: all three wire formats, JSON versus raw-code mode, usage metrics, retry exhaustion, and provider/model-separated cache keys.
- SQL: ownership persistence, parameterized values, safe identifiers, transactions, unauthorized writes, and multi-statement bypass attempts.
- Schema: added/removed fields, possible renames, changed types, uncertain all-null types, and unchanged baseline after rejection.
- Validation: null rates before aggregation, duplicate keys, coercion loss, ranges, stale data, valid forecast timestamps, and empty output.
- Anomalies: known outlier, constant series, nonnumeric input, missing values, small sample count, and zero IQR.
- Sandbox: forbidden imports, outside-path read/write, symlink escape, network attempts, child process attempts, DuckDB external access, timeout, and bounded output.

## Graph assertions

Test the complete successful node order. Verify a repaired failure returns to execution with new code and retained error history. Verify exactly three retries maximum, including alternating execution/validation failures. Equivalent fixes must not execute twice.

Plan and generation failures must stop before executing invalid code. Validation failure must preserve existing good data. Publishing failure must roll back both data and accepted schema metadata. An identical rerun must keep the business-key row count unchanged.

Check reports for accurate success, failure, and partial publication status. Verify logs include required fields and exclude secrets. The UI must not execute a new pipeline merely because a result tab changed.

## Failure-injection scenarios

Put reusable fixtures in `tests/failure_injection/scenarios.py`. Each fixture must identify a fault, the expected detection, the repair responses, and the final correctness assertion.

| Scenario | Injected condition | Acceptable recovery | Required assertion |
| --- | --- | --- | --- |
| Renamed field | Temperature source key changes | Apply a verified alias mapping | Correct canonical values; recorded drift |
| Removed field | Required humidity key disappears | Refetch a healthy later response if available | Required data restored; persistent removal fails honestly |
| New field | Source includes an additional variable | Explicitly accept or ignore the optional field | Required output unchanged; drift decision logged |
| Type change | Numeric readings arrive as strings | Convert and reject nonnumeric conversion loss | Numeric output and valid ranges |
| Null spike | Many required readings become null | Refetch valid data or use a predeclared policy | No fabricated values or hidden incomplete aggregate |
| Duplicate rows | Repeated source business keys | Apply documented deterministic deduplication | Unique output keys; intended values preserved |
| API timeout | Transient timeouts | Bounded transport retry or graph refetch | Retry counts recorded; eventual real success |
| Malformed JSON | Invalid response body | Retry and receive a valid response | Bad body not cached; valid data published |
| Out-of-range values | Impossible temperature or humidity | Recover from a valid subsequent source response | Invalid measurements never silently clipped to pass |

Include persistent variants of removed fields, null spikes, timeouts, and invalid values. Safe failure is correct behavior for an unrecoverable scenario; it is not a successful self-heal.

Also test repeated fixes, exhausted model requests, empty API results, migration rollback, duplicate reruns, and unauthorized SQL. An added optional field may be handled without an LLM repair if the policy already permits it; count that as drift handling, not evidence of generated-code repair.

## Planned commands

After tests are implemented:

```bash
python -m pytest -q
python -m pytest tests/test_tools.py -q
python -m pytest tests/test_graph.py -q
python -m pytest tests/failure_injection/test_failures.py -q
```

Record failures and meaningful limitations. Do not report passing tests from test collection alone or treat a no-tests-collected result as success.
