# Live Workflow Frontend

## Status and ownership

Frontend-first development has been requested. The assistant provides code and explanations in chat; the developer creates the application files. The first preview is now present in `app.py` and has been inspected. Runtime behavior has not been independently verified. The next requested change is the full architecture diagram with changing node colors. Result panels follow that change.

## First increment

Use Streamlit to show an animated pipeline flow, current node states, repair count, final outcome, and timestamped event log. Exercise three deterministic scenarios: success, recovery after one validation failure, and exhausted repairs.

The preview must visibly state that it simulates events. It does not invoke an LLM, call Open-Meteo, execute generated code, or publish records. The user's request is displayed as context; the preview does not interpret arbitrary requests.

Flow: plan → generate code → execute → validate → analyze → report. Validation failure enters diagnose-and-fix and returns to execute. After three failed repair attempts, report failure. Successful report generation must not turn a failed pipeline into a successful run.

## Event contract

Each event contains timestamp, node, status, message, retry count, and an optional terminal outcome. Node status is running, success, or failed. Terminal outcome is success or failed and is separate from the report node's own status.

Render events in order and keep historical errors even when a retry succeeds. Session state retains the last run across ordinary widget reruns. Session state is not durable storage: browser reload or a disconnected session may reset it.

The first increment supports one synchronous demo per browser session. Interrupting a run by editing widgets or reloading is not cancellation support; leave controls unchanged until the simulation finishes. Production run coordination and cancellation require additional design.

## Streamlit mechanism

Use an `st.empty()` container to replace the flow, counters, and log on each event. Store the view model in `st.session_state`. Replace the original status cards with the exact architecture topology from `docs/architecture.mmd`. Keep the textual event log and an active-component label alongside colors.

References: [replaceable containers](https://docs.streamlit.io/develop/api-reference/layout/st.empty) and [session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state).

## Second increment: full architecture animation

The installed environment was inspected and has Streamlit 1.67.0 with native `st.mermaid_chart`. The developer should raise the Streamlit requirement to `>=1.67,<2` when implementing this feature. No Graphviz or external Mermaid CDN is needed for this approach. See [Streamlit Mermaid documentation](https://docs.streamlit.io/develop/api-reference/charts/st.mermaid_chart).

Add `ui_flow.py` to read the diagram and append Mermaid classes per node state: pending gray, running blue, completed green, repair-in-progress orange, and failed red. Preserve the diagram's links and labels. The colors update on events; this increment does not implement moving particles or smooth edge animations.

Map low-level events to the request, entry point, LLM client, API broker, cache, sources, response snapshots, sandbox, staging database, metadata, publisher, warehouse, failure report, and run log, as well as the main workflow stages. Repeated use of a component returns it to running, then its latest outcome. Retain earlier failures in the log even if a retry turns the node green.

Use a preview state version to reset the older seven-node session state once when upgrading the code. A run starts with fresh states. During a retry, reset only affected ingestion/execution descendants; preserve upstream planning state and the error history. Publishing and anomaly nodes must remain pending when validation never passes.

The simulation explicitly performs a cache lookup that misses before visiting the source node. A completed cache lookup is not a cache hit. Generated-code execution, requests, data staging, schema checks, publication, and report generation remain simulated. Parent nodes may remain active while children run, and the log indicator stays active while events are collected in browser-session state. No JSONL log file is implied.

On exhausted retries, the failure-report node may complete successfully while the overall pipeline outcome stays failed. Distinguish node-operation success from pipeline success in both the flow and log.

## Third increment: result panels

Add `ui_results.py` for presentation helpers, a fixed synthetic dataset, illustrative quality checks, and z-score/IQR calculations on that dataset. Import its renderer in `app.py` and call it once after the event loop or retained-state display. The existing workflow view continues updating during the simulation; result tabs populate after it finishes. Keeping download widgets outside the repeated dashboard render avoids repeated widget creation in the same script run.

Tabs: Plan, Generated Code, Validation Results, Anomalies, Final Report, and Table Preview. The code tab explicitly contains a hand-authored example, not LLM-generated code. Plan and dataset are fixed Bengaluru fixtures regardless of request text. Show failed validation attempts in the history even after recovery. For the exhausted-retries scenario, display the rejected duplicate fixture and skip anomaly analysis.

Provide a provider dropdown marked as preview-only. Capture its value at run start so changing the dropdown afterward does not relabel the previous report. The Markdown download must identify the simulation, selected preview provider, final outcome, repairs, fixture rows, and zero warehouse writes. Statistical calculations on fixtures do not verify the future backend anomaly tool.

## Remaining increments

1. Implement and verify the architecture animation.
2. Add and verify the result panels.
3. Connect actual LangGraph events and tool-start/tool-end events when the backend exists.
4. Persist real reports and logs, prevent conflicting warehouse writes, and verify failure/partial-success states.

LangGraph node updates generally describe completed node work. A live running indicator needs an event emitted at node start, plus heartbeats or granular tool events for long operations. Do not present simulated delays or estimated percentages as real backend progress.

## Manual acceptance checks

- Success: all main stages complete and repair count stays zero.
- Recovery: a validation failure remains in the log; diagnosis runs once; execution and validation rerun; the final outcome succeeds.
- Exhaustion: three repairs are attempted; analysis stays pending; report generation completes but the final outcome remains failed.
- Rerun: starting a new simulation resets its states and log.
- Ordinary widget changes after completion retain the previous run until another simulation starts.
- No credentials are required, no external requests occur, and no warehouse is modified.

Additional result-panel checks: successful scenarios show a synthetic outlier; exhausted retries retain a duplicate row and no analysis; downloading a report does not start another simulation; changing the provider afterward preserves the previous run's captured provider.

Launch from the project directory with `python -m streamlit run app.py`.
