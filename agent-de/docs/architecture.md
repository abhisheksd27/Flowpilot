# Architecture

FlowPilot implements a bounded LangGraph workflow: plan → generate_code → execute → validate/publish → anomaly_detect → report. Execution or validation errors route through diagnose_and_fix, with at most three repairs. Unsafe or repeated repairs terminate with a failure report.

The host brokers allowlisted API calls, preserves immutable response snapshots, and sends those snapshots to an isolated worker. Generated Python transforms only these inputs into an attempt-specific staging DuckDB database. Pandera, SQL checks, source reconciliation, and accepted schemas gate publication. One transaction upserts validated hourly records, rebuilds daily aggregates, and records ownership/schema metadata. A process lock serializes writers.

The CLI, Streamlit worker thread, and daily scheduler call the same run_pipeline function. Structured events drive the persistent dark SVG; the frontend does not invent backend progress. See [diagram](architecture.mmd), [security](security.md), and [workflow](workflow.md).

The default built-in planner and repair engine use deterministic templates, so real ingestion requires no model account. Gemini, Groq, and Ollama adapters support model-generated plans/code within the same fixed environmental contract. This is not an arbitrary API discovery agent.
