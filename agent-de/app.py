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
from pipeline.cities import CITIES, city_result, city_request, run_city

st.set_page_config(page_title="FlowPilot", page_icon="🔄", layout="wide")
settings = Settings.from_env()
settings.prepare()
selected_city = st.sidebar.selectbox("Choose a city", CITIES, disabled="run_queue" in st.session_state)


def latest_result() -> dict:
    """Read an atomically saved result, including runs produced by the scheduler."""
    try:
        return city_result(settings, selected_city)
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


def start_run(city: str, provider: str, request: str) -> None:
    """Run blocking tools off the UI thread, forwarding real events through a queue."""
    messages = queue.Queue()
    selected = replace(settings, provider=provider)
    st.session_state["run_queue"] = messages
    st.session_state["result"] = {}
    st.session_state["view"] = view_from_result({"status": "running", "user_request": request})
    def worker():
        from agent.graph import run_pipeline
        try:
            result = run_city(city, selected, request=request, on_event=lambda event: messages.put(("event", event)))
            messages.put(("result", result))
        except Exception as error:
            messages.put(("result", {"status": "failed", "errors": [str(error)],
                                     "user_request": request, "final_report": f"# Pipeline failed\n\n{error}"}))
    thread = threading.Thread(target=worker, daemon=True, name="flowpilot-run")
    st.session_state["run_thread"] = thread
    thread.start()


if st.session_state.get("app_version") != 4 or st.session_state.get("result_city") != selected_city:
    st.session_state["result_city"] = selected_city
    st.session_state["app_version"] = 4
    st.session_state["result"] = latest_result()
    st.session_state["view"] = view_from_result(st.session_state["result"])

if st.session_state.get("request_city") != selected_city:
    st.session_state["request_city"] = selected_city
    st.session_state["request_text"] = city_request(selected_city)

st.markdown("""<style>
.stApp {background:#080f1f;color:#e2e8f0}
[data-testid="stSidebar"] {background:#101c2e}
.block-container {padding-top:4.5rem;max-width:1400px}
.fp-hero {padding:28px 32px;border:1px solid #284159;border-radius:4px;background:#101c22;margin-bottom:22px}
.fp-kicker {color:#75dfc3;font-size:12px;letter-spacing:2px;text-transform:uppercase}
.fp-hero h1 {font-size:32px;letter-spacing:-1.5px;margin:8px 0}
.fp-hero p {max-width:850px;color:#b6c7db;font-size:15px;line-height:1.7}
[data-testid="stMetric"] {background:#101e31;border:1px solid #27394f;border-radius:4px;padding:16px}
button:focus-visible,a:focus-visible {outline:3px solid #7dd3fc;outline-offset:3px}
@media(max-width:650px){.fp-hero{padding:20px}.fp-hero h1{font-size:34px}}
</style><section class="fp-hero"><div class="fp-kicker">Weather & air quality</div>
<h1>FlowPilot</h1><p>Hourly weather and air-quality records for your city, checked for missing values and unusual changes.</p></section>""", unsafe_allow_html=True)
with st.expander("What does this do — and how is it useful?", expanded=False):
    st.markdown("""**Less manual work.** Fresh data arrives automatically, ready for analysis and reporting.

**More trustworthy results.** Quality checks catch gaps, duplicates, and invalid values before they reach your tables. If a safe repair is not possible, the run fails and preserves previously validated data.

**Easier investigation.** Charts and statistical flags help you explore changes in temperature, humidity, and PM2.5. Daily summaries make it easier to compare days.

**A visible learning tool.** Follow the flow below to see how a real data pipeline collects, checks, stores, and analyzes information.

The sources provide modeled estimates, not direct sensor readings. An anomaly is a signal to investigate, not a confirmed incident.""")
with st.sidebar:
    st.header("Your workspace")
    st.caption("Choose a city, describe what you need, then refresh the data.")
    provider = st.selectbox("Processing engine", ("builtin", "ollama", "gemini", "groq"),
                           index=("builtin", "ollama", "gemini", "groq").index(settings.provider),
                           format_func=lambda value: {"builtin": "Built-in · no API key needed", "ollama": "Ollama · local model", "gemini": "Gemini", "groq": "Groq"}[value])
    st.caption("Built-in uses deterministic rules and real data. Model providers require their configured service or key.")
    request = st.text_area(
        "What would you like to track?",
        key="request_text",
        height=90,
        placeholder=f"Example: Track daily weather and air quality for {selected_city} and flag anomalies.",
        help="Keep the selected city in your request. FlowPilot currently supports weather, humidity, and air-quality analysis.",
    )
    running = "run_queue" in st.session_state
    if st.button("Refresh data now", type="primary", disabled=running or not request.strip()):
        start_run(selected_city, provider, request)
        st.rerun()
    if st.button("Show latest saved results", disabled=running):
        st.session_state["result"] = latest_result()
        st.session_state["view"] = view_from_result(st.session_state["result"])
        st.rerun()
    st.divider()
    st.subheader("Local automation")
    st.caption("The local schedule tracks Bengaluru. Refresh other cities manually here; the public dashboard updates all six cities hourly.")
    schedule = scheduler_status(settings)
    st.write("Status:", {"waiting": "Active · waiting for next update", "running_pipeline": "Updating data", "not_started": "Not started", "stopped": "Stopped", "stale_or_stopped": "Needs attention"}.get(schedule.get("status"), "Unknown"))
    frequency = schedule.get("frequency", settings.schedule_frequency)
    cadence = "Every hour, at minute 00" if frequency == "hourly" else schedule.get("schedule", settings.schedule_time)
    st.caption(f"Schedule: {cadence} · {schedule.get('timezone', settings.schedule_timezone)}")
    if schedule.get("next_run_utc"):
        st.write("Next run:", pd.Timestamp(schedule["next_run_utc"]).tz_convert(settings.schedule_timezone).strftime("%d %b %Y, %H:%M %Z"))
    if schedule.get("last_run"):
        last_run = schedule["last_run"]
        finished = pd.Timestamp(last_run["finished_at"]).tz_convert(settings.schedule_timezone).strftime("%d %b, %H:%M %Z")
        st.caption(f"Last automatic update: {finished} · {last_run['status']}")
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
    a.metric("Data update", {"success": "Ready", "running": "Updating", "idle": "Not started", "failed": "Needs attention"}.get(view["outcome"], view["outcome"].capitalize()))
    b.metric("Automatic repairs", f"{view['retry_count']} / 3")
    c.metric("Steps recorded", len(view["events"]))
    with st.container(height=100, border=False):
        if view["outcome"] == "success":
            st.success("Your data passed validation and is ready to explore.")
        elif view["outcome"] in {"failed", "partial"}:
            st.error("Run " + view["outcome"] + ". Review the report and errors; previously validated data is preserved.")
        else:
            active = [NODE_LABELS[n] for n, v in view["statuses"].items() if v == "running"]
            st.info("Active: " + " · ".join(active) if active else "Ready to fetch real Open-Meteo data.")
    st.subheader("Follow your data")
    st.caption("Collect → check → save → analyze. Blue means working, green means completed, orange means repairing, and red means a failure.")
    render_flow(view["statuses"])
    with st.expander("Live event log", expanded=bool(messages)):
        columns = ("timestamp", "node", "status", "message", "retry_count", "duration")
        st.dataframe([{k: e.get(k) for k in columns} for e in view["events"][-40:]],
                     width="stretch", hide_index=True, height=280)
    if finished:
        st.rerun()


if "run_queue" not in st.session_state:
    st.subheader(f"Your latest results · {selected_city}")
    result = st.session_state["result"]
    if result:
        st.caption("Latest saved run: " + result.get("run_id", "Unknown") + " · Use ‘Show latest saved results’ after an automatic update.")
    render_results(result, settings)
    st.divider()
live_dashboard()
