# Tools and code map

| Module | Responsibility |
| --- | --- |
| agent/graph.py | LangGraph orchestration, bounded repair, run artifacts |
| agent/llm.py | Built-in/Gemini/Groq/Ollama adapters and usage/cache |
| pipeline/contracts.py | Fixed source/target contracts and trusted reconciliation |
| tools/api_tool.py | Allowlisted HTTP, response bounds, cache and retries |
| tools/python_sandbox.py | Policy validation and OS/container worker launcher |
| tools/_sandbox_worker.py | Approved snapshot access and staged loading |
| tools/validate_tool.py | Pandera and SQL quality checks |
| tools/schema_tool.py | Schema inspection, drift comparison and accepted schema |
| tools/sql_tool.py | Parsed, bounded, ownership-checked SQL |
| pipeline/warehouse.py | Single writer lock and atomic silver/gold publication |
| tools/anomaly_tool.py | Z-score and IQR analysis |
| pipeline/events.py | Structured events and atomic JSON artifacts |
| pipeline/scheduler.py | Timezone-aware daily daemon and macOS installation |
| main.py | CLI run/preview/watch/status/schedule |
| app.py / ui_results.py / ui_flow.py | Actual events, results and animated flow |

Generated code uses brokered `call_api` snapshots and `load_frame`; it never receives production SQL write access. Source edits must retain both validation and reconciliation before publish.
