# Architecture

## Status and purpose

This document is the implementation design. It does not claim that the full system currently runs. See the [implementation plan](implementation-plan.md) for progress.

The system converts a request into this sequence:

Request → Plan → Ingest → Transform → Stage → Validate → Publish → Analyze → Report

Failure during execution or validation enters a bounded repair loop. The validated warehouse remains separate from failed attempts.

## Components

| Component | File | Responsibility |
| --- | --- | --- |
| CLI | `main.py` | Accept a request, run the graph, save and display a report |
| Web UI | `app.py` | Configure a run and display streamed node updates |
| Configuration | `config.py` | Resolve provider settings and runtime paths |
| Workflow | `agent/graph.py` | Coordinate nodes and route success or failure |
| Typed state | `agent/state.py` | Define the shared execution record |
| Prompts and catalog | `agent/prompts.py` | Define allowed sources and model instructions |
| LLM interface | `agent/llm.py` | Adapt providers and count calls, tokens, and cache hits |
| API broker | `tools/api_tool.py` | Restrict endpoints and fetch/cache approved responses |
| Python runner | `tools/python_sandbox.py` | Execute generated code with enforced isolation |
| SQL tool | `tools/sql_tool.py` | Query DuckDB under table and statement permissions |
| Schema tool | `tools/schema_tool.py` | Inspect schema and compare it with accepted versions |
| Validation tool | `tools/validate_tool.py` | Check raw input completeness and staged output quality |
| Anomaly tool | `tools/anomaly_tool.py` | Compute z-score and IQR flags |
| Evaluator | `eval/run_eval.py` | Run deterministic scenarios and record measured results |

## Control and data boundaries

LangGraph controls order and retries. Tools perform bounded operations and return structured results. Tools must be independently testable without a live LLM.

The LLM proposes plans, code, and repairs. The host validates those proposals; model output cannot grant permission or change security limits.

The host API broker fetches requests from the validated plan. Generated Python accesses the fetched responses through an injected interface. A sandbox adapter for `requests.get` may serve those exact approved requests, but it must not expose a general network-capable Requests session. Requests outside the approved set are rejected.

An execution attempt has its own directory and staging DuckDB file. Generated code loads into staging. Validation and a trusted publishing operation control access to the main warehouse. This preserves the requested load-before-validation sequence without exposing good data to failed transforms.

## Graph structure

The graph retains the required nodes:

`plan → generate_code → execute → validate → anomaly_detect → report`

Execution and validation failures route to `diagnose_and_fix`, then back to `execute`. Publishing is a transactional operation inside the successful validation path. It need not be a separate LangGraph node.

Planning and code-generation failures retry their own steps within their budgets. They must not route to execution with an empty or invalid plan or program.

## Important design decisions

### Validate proposals before acting

Validate required JSON fields, supported API endpoints and parameters, identifiers, supported transformations, business keys, and data-quality rules. Coordinates come from geocoding, not model guesses.

### Keep publishing idempotent

Upsert records by the plan's business key in a transaction. Preserve history outside the incoming scope. An identical rerun must not add duplicate records. Generated staging code must also be safe to rerun on its own target.

### Separate schema observation from acceptance

Track raw source schema and final table schema separately. A source rename can be repaired while leaving the canonical warehouse schema unchanged. A new source field must not silently erase the previous expected schema.

Record proposed changes, repair decisions, migration results, and accepted versions. Possible renames require evidence. Preserve the old table version when a structural migration could lose information.

### Bound recovery

Allow at most three retries after a step's initial attempt. Execution and validation share one repair budget so alternating failures cannot reset it. Record all fixes and reject equivalent normalized programs.

### Report what actually happened

A failure report distinguishes execution failure, validation failure, publishing failure, and analysis failure after publishing. If data was committed before analysis failed, report that fact explicitly.

## Storage

```text
data/
├── pipeline.duckdb       # Validated tables and accepted metadata
├── cache/
│   ├── api/              # Successful API JSON responses
│   └── llm/              # Successful provider response text
├── logs/                # run_<id>.jsonl
├── runs/                # Per-attempt staging and diagnostic artifacts
└── reports/             # Final Markdown reports
```

Paths are relative to the configured data directory. Treat runtime artifacts as potentially sensitive local data. Never place provider secrets in the sandbox environment or execution payload.

## Operating assumptions

One warehouse writer is supported initially. No background scheduling is implied. Each plan records timezones, source time semantics, aggregation frequency, and missing-data policy. Short data windows limit the strength of anomaly analysis.

The [diagram source](architecture.mmd), [workflow](workflow.md), and [security requirements](security.md) provide the next level of detail.
