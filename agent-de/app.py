"""Live FlowPilot console: actual workflow events, warehouse data, and scheduled runs."""
from dataclasses import replace
from datetime import datetime
import json
import queue
import threading
from pathlib import Path
import pandas as pd
import streamlit as st
from config import DEFAULT_REQUEST, Settings
from pipeline.scheduler import scheduler_status
from pipeline.warehouse import preview
from tools.sql_tool import run_sql
from ui_flow import NODE_LABELS, render_flow
from ui_results import render_results

st.set_page_config(page_title="FlowPilot", page_icon="🔄", layout="wide")
settings = Settings.from_env()
settings.prepare()


def latest_result() -> dict:
    """Read an atomically saved result, including runs produced by the scheduler."""
    path = settings.data_dir / "latest.json"
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (ValueError, OSError):
        return {}


def view_from_result(result: dict) -> dict:
    """Restore actual historical node states; never animate fabricated progress."""
    view = {"statuses": {n: "pending" for n in NODE_LABELS}, "events": [], "retry_count": 0,
            "outcome": result.get("status", "idle"), "request": result.get("user_request", "")}
    for event in result.get("step_history", []):
        if event["node"] in view["statuses"]:
            view["statuses"][event["node"]] = event["status"]
        view["events"].append(event)
        view["retry_count"] = event["retry_count"]
    return view


def start_run(request: str, provider: str) -> None:
    """Run blocking tools off the UI thread, forwarding real events through a queue."""
    messages = queue.Queue()
    selected = replace(settings, provider=provider)
    st.session_state["run_queue"] = messages
    st.session_state["result"] = {}
    st.session_state["view"] = view_from_result({"status": "running", "user_request": request})
    def worker():
        from agent.graph import run_pipeline
        try:
            result = run_pipeline(request, selected, on_event=lambda event: messages.put(("event", event)))
            messages.put(("result", result))
        except Exception as error:
            messages.put(("result", {"status": "failed", "errors": [str(error)],
                                     "user_request": request, "final_report": f"# Pipeline failed\n\n{error}"}))
    thread = threading.Thread(target=worker, daemon=True, name="flowpilot-run")
    st.session_state["run_thread"] = thread
    thread.start()


if st.session_state.get("app_version") != 3:
    st.session_state["app_version"] = 3
    st.session_state["result"] = latest_result()
    st.session_state["view"] = view_from_result(st.session_state["result"])

st.title("FlowPilot")
st.caption("Real environmental data engineering · Bronze → Silver → Gold · Bengaluru hourly")
with st.sidebar:
    st.header("Pipeline controls")
    provider = st.selectbox("Planning and repair engine", ("builtin", "ollama", "gemini", "groq"),
                           index=("builtin", "ollama", "gemini", "groq").index(settings.provider))
    st.caption("Built-in uses deterministic rules and real data. Model providers require their configured service or key.")
    request = st.text_area("Data request", value=DEFAULT_REQUEST, height=130)
    running = "run_queue" in st.session_state
    if st.button("Run real pipeline", type="primary", disabled=running or not request.strip()):
        start_run(request.strip(), provider)
        st.rerun()
    if st.button("Load latest scheduled result", disabled=running):
        st.session_state["result"] = latest_result()
        st.session_state["view"] = view_from_result(st.session_state["result"])
        st.rerun()
    st.divider()
    st.subheader("Scheduled automation")
    schedule = scheduler_status(settings)
    st.write("Service:", schedule.get("status", "not_started"))
    frequency = schedule.get("frequency", settings.schedule_frequency)
    cadence = "Every hour, at minute 00" if frequency == "hourly" else schedule.get("schedule", settings.schedule_time)
    st.caption(f"Schedule: {cadence} · {schedule.get("timezone", settings.schedule_timezone)}")
    if schedule.get("next_run_utc"):
        st.write("Next run:", pd.Timestamp(schedule["next_run_utc"]).tz_convert(settings.schedule_timezone).strftime("%d %b %Y, %H:%M %Z"))
    if schedule.get("last_run"):
        st.json(schedule["last_run"])
    st.caption("Automatic runs need this computer awake and the project drive mounted. The UI may be closed.")


@st.fragment(run_every=0.2 if "run_queue" in st.session_state else None)
def live_dashboard():
    """Consume actual events while retaining one SVG and a fixed status region."""
    view = st.session_state["view"]
    finished = False
    messages = st.session_state.get("run_queue")
    if messages is not None:
        # Limit batches to retain visible transitions without inventing delays.
        for _ in range(3):
            try:
                kind, item = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "result":
                st.session_state["result"] = item
                view["outcome"] = item["status"]
                del st.session_state["run_queue"]
                finished = True
                break
            node = item["node"]
            if node == "execute" and item["status"] == "running":
                for name in ("api", "cache", "sources", "snapshots", "sandbox", "staging", "validate", "metadata"):
                    view["statuses"][name] = "pending"
            if node in view["statuses"]:
                view["statuses"][node] = item["status"]
            view["events"].append(item)
            view["retry_count"] = item["retry_count"]
            view["outcome"] = item.get("outcome") or "running"
    a, b, c = st.columns(3)
    a.metric("Run outcome", view["outcome"].capitalize())
    b.metric("Repair attempts", f"{view['retry_count']} / 3")
    c.metric("Real tool events", len(view["events"]))
    with st.container(height=100, border=False):
        if view["outcome"] == "success":
            st.success("Real data validated, published, and analyzed. Results are below the live flow.")
        elif view["outcome"] in {"failed", "partial"}:
            st.error("Run " + view["outcome"] + ". Review the report and errors; previously validated data is preserved.")
        else:
            active = [NODE_LABELS[n] for n, v in view["statuses"].items() if v == "running"]
            st.info("Active: " + " · ".join(active) if active else "Ready to fetch real Open-Meteo data.")
    st.subheader("Live pipeline architecture")
    render_flow(view["statuses"])
    with st.expander("Live event log", expanded=bool(messages)):
        columns = ("timestamp", "node", "status", "message", "retry_count", "duration")
        st.dataframe([{k: e.get(k) for k in columns} for e in view["events"][-40:]],
                     width="stretch", hide_index=True, height=280)
    if finished:
        st.rerun()


live_dashboard()
if "run_queue" not in st.session_state:
    render_results(st.session_state["result"], settings)
