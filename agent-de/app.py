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
            result = run_city(city, selected, request=request, refresh=True, on_event=lambda event: messages.put(("event", event)))
            messages.put(("result", result))
        except Exception as error:
            messages.put(("result", {"status": "failed", "errors": [str(error)],
                                     "user_request": request, "final_report": f"# Pipeline failed\n\n{error}"}))
    thread = threading.Thread(target=worker, daemon=True, name="flowpilot-run")
    st.session_state["run_thread"] = thread
    thread.start()


if st.session_state.get("app_version") != 5 or st.session_state.get("result_city") != selected_city:
    st.session_state["result_city"] = selected_city
    st.session_state["app_version"] = 5
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
st.subheader("Ask about current weather")
with st.form("temperature-question"):
    question = st.text_input("Your question", "What is the current temperature in Bangalore?", max_chars=300)
    ask = st.form_submit_button("Get weather", disabled="run_queue" in st.session_state)
if ask:
    try:
        from pipeline.current_weather import answer_temperature
        import re
        with st.status("Weather lookup: checking city and fetching Open-Meteo…", expanded=True) as lookup:
            if re.search(r'tomorrow|weekend|forecast|next week', question, re.I):
                from pipeline.forecasts import forecast
                normalized = re.sub(r'\b(bangalore|banglore)\b', 'Bengaluru', question, flags=re.I)
                cities = [name for name in CITIES if re.search(r'\b' + name + r'\b', normalized, re.I)]
                if len(cities) > 1:
                    raise ValueError('Ask for one city forecast at a time')
                city = cities[0] if cities else selected_city
                st.session_state['temperature_answer'] = {'forecast': forecast(question, city, settings)}
            elif re.search(r'today.*(hotter|warmer|colder).*yesterday|how many hours', question, re.I):
                from pipeline.analytics import ask_saved
                st.session_state['temperature_answer'] = {'saved': ask_saved(question, selected_city, settings)}
            else:
                st.session_state['temperature_answer'] = answer_temperature(question, settings, default_city=selected_city)
            st.write("City resolved → fresh current-weather response received → answer prepared")
            lookup.update(label="Weather lookup completed", state="complete", expanded=False)
        st.session_state.pop('temperature_error', None)
    except Exception as error:
        st.session_state.pop('temperature_answer', None)
        st.session_state['temperature_error'] = str(error)
if st.session_state.get('temperature_error'):
    st.error(st.session_state['temperature_error'])
if st.session_state.get('temperature_answer', {}).get('forecast'):
    forecast_answer = st.session_state['temperature_answer']['forecast']
    st.success(forecast_answer['city'] + '\n\n' + forecast_answer['answer'])
    st.dataframe(forecast_answer['days'], hide_index=True)
    st.caption('Open-Meteo forecast · Retrieved ' + forecast_answer['issued_at'] + ' · Probabilities are forecasts, not guarantees.')
elif st.session_state.get('temperature_answer', {}).get('saved'):
    saved_answer = st.session_state['temperature_answer']['saved']
    st.success(saved_answer['answer'])
    st.dataframe(saved_answer['days'], hide_index=True)
elif st.session_state.get('temperature_answer'):
    answer = st.session_state['temperature_answer']
    st.success(answer.get('answer', f"Temperature in {answer['city']}: {answer['temperature']:.1f} {answer['unit']}"))
    fields = {'apparent_temperature': 'Feels like', 'relative_humidity_2m': 'Humidity', 'rain': 'Rain', 'showers': 'Showers', 'precipitation': 'Precipitation', 'snowfall': 'Snowfall', 'cloud_cover': 'Cloud cover', 'wind_speed_10m': 'Wind speed', 'wind_direction_10m': 'Wind direction', 'wind_gusts_10m': 'Wind gusts'}
    st.dataframe([{'Detail': label, 'Value': answer.get('current', {}).get(field, 'Unavailable'), 'Unit': answer.get('units', {}).get(field, '')} for field, label in fields.items()], hide_index=True, width="stretch")
    st.caption(f"Source: Open-Meteo · Measurement time: {answer['time']} ({answer['timezone']}) · Fetched fresh when you clicked Get weather. This answer does not run or update the warehouse pipeline.")
with st.sidebar:
    st.header("Your workspace")
    st.caption(f"Execution: {'trusted lightweight mode' if settings.demo_mode else settings.sandbox_backend + ' isolation'} · Data: real Open-Meteo responses")
    st.caption("Choose a city, describe what you need, then refresh the data.")
    advanced = st.checkbox("Advanced options", value=False, disabled="run_queue" in st.session_state)
    engines = ("builtin",) if settings.demo_mode or not advanced else ("builtin", "ollama", "gemini", "groq")
    provider = st.selectbox("Processing engine", engines,
                           index=0,
                           format_func=lambda value: {"builtin": "Built-in · no API key needed", "ollama": "Ollama · local model", "gemini": "Gemini", "groq": "Groq"}[value])
    if advanced:
        st.caption("AI providers are experimental and can fail to generate valid transformations. Built-in runs the tested transformation with real data.")
    request = st.text_area(
        "What would you like to track?",
        key="request_text",
        height=90,
        disabled="run_queue" in st.session_state,
        placeholder=f"Example: Track daily weather and air quality for {selected_city} and flag anomalies.",
        help="Keep the selected city in your request. FlowPilot currently supports weather, humidity, and air-quality analysis.",
    )
    running = "run_queue" in st.session_state
    if st.button("Run pipeline now", type="primary", disabled=running or not request.strip()):
        start_run(selected_city, provider, request)
        st.rerun()
    if st.button("Show latest saved results", disabled=running):
        st.session_state["result"] = latest_result()
        st.session_state["view"] = view_from_result(st.session_state["result"])
        st.rerun()
    st.divider()
    st.caption("Get weather answers above, or use Refresh data now to run the full data pipeline. Saved results include their original timestamps.")


@st.fragment(run_every=30)
def hourly_status():
    schedule = scheduler_status(settings)
    with st.expander('Hourly collection status', expanded=True):
        st.write('Scheduler:', schedule.get('status', 'not started'))
        if schedule.get('next_run_utc'):
            st.write('Next update:', pd.Timestamp(schedule['next_run_utc']).tz_convert(settings.schedule_timezone).strftime('%d %b %Y %H:%M %Z'))
        if schedule.get('last_run'):
            last = schedule['last_run']
            st.write('Last run:', last['status'], '·', last['run_id'])
        if schedule.get('last_error'):
            st.warning(schedule['last_error'])
        try:
            from pipeline.operations import check_alerts
            health = check_alerts(settings, selected_city)
            if health['stale']:
                st.warning('Saved weather data is stale or missing for ' + selected_city)
            if health['latest_status'] in ('failed', 'partial'):
                st.error('Latest pipeline issue: ' + '\n'.join(health['errors']))
                if st.session_state.get('notified_failure') != health['latest_run']:
                    st.toast('Pipeline failed. Open Operations for the exact error.', icon='⚠️')
                    st.session_state['notified_failure'] = health['latest_run']
        except Exception as error:
            st.caption('Health status temporarily unavailable: ' + str(error))
        st.caption('Hourly background collection tracks Bengaluru. Data quality checks and anomaly analysis run before reporting success. Click Show latest saved results to load a completed update. Your computer must remain awake.')


hourly_status()


@st.fragment(run_every=0.2 if "run_queue" in st.session_state else None)
def live_dashboard():
    """Consume actual events while retaining one SVG and a fixed status region."""
    view = st.session_state["view"]
    finished = False
    messages = st.session_state.get("run_queue")
    if messages is not None:
        # Limit batches to retain visible transitions without inventing delays.
        for _ in range(1):
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


live_dashboard()
with st.expander('Explore forecasts, data tools and pipeline operations', expanded=False):
    from ui_workspace import render_workspace
    render_workspace(settings, selected_city)
if "run_queue" not in st.session_state:
    st.subheader(f"Your latest results · {selected_city}")
    result = st.session_state["result"]
    if result:
        st.caption("Latest saved run: " + result.get("run_id", "Unknown") + " · Use ‘Show latest saved results’ after an automatic update.")
    if advanced:
        render_results(result, settings)
    elif result:
        if result.get('status') == 'success':
            st.success('Data validated and saved.')
        else:
            st.warning('The last saved run failed. Refresh with the built-in engine to try again.')
        st.markdown(result.get('final_report', 'No report available yet.'))
        if result.get('final_report'):
            st.download_button('Download report', result['final_report'], file_name='flowpilot-report.md')
        st.caption('Enable Advanced options for charts, quality checks, generated code, SQL and history.')
    st.divider()
