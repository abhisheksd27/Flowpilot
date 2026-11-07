# Implementation Plan

## Working agreement

The developer writes implementation code and runs the implementation checks. The assistant writes documentation and supplies explanations, code guidance, and reviews when requested. Documentation work does not authorize editing application code.

Keep documentation synchronized after each completed step. Mark functionality complete only after the relevant behavior has been checked. Do not count starter files as verified implementation.

## Progress and sequence

| Step | Focus | Current status | Completion criteria |
| --- | --- | --- | --- |
| 1 | Python environment and dependencies | Complete, developer-confirmed | Python 3.11 and dependency import check succeed |
| 2 | Architecture and workflow documentation | Written | Component boundaries, flow, and failure rules are documented |
| 3 | Configuration | Starter exists; review next | Paths, provider selection, precedence, and invalid settings verified |
| 4 | API ingestion and caching | Starters exist; verification pending | Approved requests work; cache, timeout, malformed JSON, and URL restrictions tested |
| 5 | DuckDB and SQL permissions | Planned | Ownership enforced; transactions and idempotent writes tested |
| 6 | Schemas and validation | Planned | Quality rules, source completeness, and migrations tested |
| 7 | Anomaly detection | Planned | Numeric baseline, thresholds, small samples, and constants handled |
| 8 | LLM adapters and prompts | Adapter starter exists; prompts planned | Three adapters share a contract; mocks test formats, caching, and retries |
| 9 | Python sandbox | Planned | Isolation, timeout, import policy, and API bridge verified |
| 10 | LangGraph orchestration | Planned | Success path, bounded repair, repetition detection, and graceful failure tested |
| 11 | CLI and Streamlit | Planned | Entry points, streamed log, tabs, preview, and download verified |
| 12 | Failure evaluation and documentation review | Planned | Nine scenarios measured; results and runnable instructions documented |

Write meaningful tests alongside each component. Step 12 assembles the full evaluation; it is not the first point at which testing begins.

## Format for each coding step

1. Explain the component's purpose and prerequisites.
2. Define its input, output, and failure contract.
3. Identify files for the developer to implement.
4. Supply focused implementation guidance.
5. Run the relevant checks and inspect actual results.
6. Update the documentation to reflect verified behavior.

## Next step: configuration

Read `config.py` alongside [setup.md](setup.md). Confirm why configuration is shared by the CLI, UI, tools, and tests. Check `.env` precedence and project-relative data paths. Review settings validation before adding more components.

The existing `config.py`, API, cache, and LLM starters were created before the development responsibilities changed. They remain available for the developer to keep, adapt, or replace.
