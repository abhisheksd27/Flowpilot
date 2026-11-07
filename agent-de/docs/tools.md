# Tool Interfaces

The API, cache, and LLM sections describe existing starters inspected in the workspace. Other sections are proposed implementation contracts and have not been tested.

## API access: existing starter

`call_api(url, params, settings=None) -> dict`

`APITool(settings, session=None).call_api(url, params) -> dict`

Accepted URLs:

| URL | Purpose |
| --- | --- |
| `https://api.open-meteo.com/v1/forecast` | Weather |
| `https://air-quality-api.open-meteo.com/v1/air-quality` | Air quality |
| `https://geocoding-api.open-meteo.com/v1/search` | Location resolution |

Parameters are passed separately. The current URL check rejects embedded credentials, query strings, fragments, noncatalog paths, and ports other than 443. Redirects are not followed. Successful dictionary responses are cached by URL and parameters.

The starter retries Requests errors and invalid JSON/object responses, except most 4xx errors; 429 remains retryable. Metrics include requests, cache hits, and retries. Response-size rejection currently occurs after downloading the response. Implement streaming enforcement before claiming a hard network memory limit.

Parameter allowlists, source-specific shape validation, redirect-as-terminal handling, and detailed request logging still need review and tests. Do not assume the existing URL restriction implements all plan-validation requirements.

## Disk cache: existing starter

`digest(value) -> str` creates a deterministic SHA-256 key from JSON serialization.

`DiskCache(directory, ttl).get(key)` returns a fresh cached value or `None`. `put(key, value)` writes a temporary file and replaces the entry atomically. Validate corrupted-envelope behavior with tests; do not assume all possible malformed cache values are covered by the starter.

LLM cache keys include provider, endpoint, model/request body, prompts, and response-format settings. Caching syntactically valid model output does not prove it is semantically correct. Repair prompts must include failures so they do not simply retrieve the same rejected answer.

## LLM interface: existing starter

`LLMClient.complete(system, prompt, *, json_mode=True) -> str`

Implementations: `GeminiClient`, `GroqClient`, `OllamaClient`. `make_client(settings)` chooses one. Metrics include calls, cache hits, input/output tokens, and transport retries. Missing hosted-provider keys fail explicitly.

Call with `json_mode=False` for raw code generation and with JSON mode for plans and repair objects. Structured JSON still needs host-side schema validation.

## Python execution: planned

Public operation: `run_python(code)` with host-bound settings and an execution context containing approved requests and the assigned staging location. Choose dependency injection rather than reading mutable global configuration.

Result fields: success status, exit code, stdout, stderr, error category, duration, timeout flag, and staging path. Expected operational failures return structured results for the graph. Setup and policy failures must be distinguishable from transform errors.

Imports are limited to `pandas`, `numpy`, `duckdb`, `requests`, `json`, `datetime`, and `math`. Imported capabilities still need restriction: Requests is brokered and DuckDB cannot access arbitrary files or extensions. See [security.md](security.md).

## SQL execution: planned

Public operation: `run_sql(query)` against a host-bound database and ownership context, with parameter binding supported by the implementation.

Return rows, column information, and operation status. Parse SQL before execution. Reject unauthorized modifications and access to files, extensions, attachments, or security settings. Statements must be authorized as a whole, including multi-statement and nested constructs.

Explicit destructive-operation permission comes only from trusted caller configuration, never LLM text or an SQL comment. See [security.md](security.md) for the permission matrix.

## Schema inspection: planned

`inspect_schema(table)` returns columns, types, row count, and a bounded sample. Resolve and quote identifiers safely. A schema comparison operation returns added, removed, changed, and possible-renamed fields without modifying the accepted baseline.

## Validation: planned

`validate_data(table)` uses host-bound plan rules, database, and expected schemas. Return `valid`, per-check results, failure details, null percentages, duplicate counts, freshness information, and drift diff. Include source completeness rather than validating only aggregates.

## Anomalies: planned

`detect_anomalies(table, column)` returns the method settings, sample count, thresholds, and flagged records with key/time/value. Return an explicit status for insufficient samples, nonnumeric data, zero variance, or degenerate IQR. Do not silently convert an undefined calculation into a successful empty result.
