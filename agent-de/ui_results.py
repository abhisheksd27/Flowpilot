"""Actual pipeline artifacts, quality checks, anomaly charts, and warehouse exploration."""
import json
import pandas as pd
import streamlit as st
from config import Settings
from pipeline.warehouse import preview
from tools.sql_tool import run_sql


def render_results(result: dict, settings: Settings) -> None:
    """Display real persisted results; never substitute fixture or sample measurements."""
    tabs = st.tabs(["Overview", "Plan", "Generated code", "Quality checks", "Trends & flags", "Report", "Browse data", "History"])
    with tabs[0]:
        if not result:
            st.info("Start with ‘Refresh data now’ in the sidebar. Your measurements, quality checks, and report will appear here.")
        else:
            outcome = result.get("status", "unknown")
            if outcome == "success":
                st.success("Ready to explore · this update passed its quality checks.")
            else:
                st.warning("This update needs attention. Open Report for the cause and any attempted repairs.")
            published = result.get("published") or {}
            analyses = result.get("anomalies") or {}
            a, b, c = st.columns(3)
            a.metric("Hours in this update", published.get("hourly_rows", "—"))
            b.metric("Daily summaries", published.get("daily_rows", "—"))
            c.metric("Unusual values flagged", sum(item.get("count", 0) for item in analyses.values()) if analyses else "—")
            frame = preview(settings, "silver_environment", 5000)
            if not frame.empty:
                location = result.get("plan", {}).get("location_id")
                if location:
                    frame = frame[frame["location_id"] == location]
                frame = frame.sort_values("time")
                if not frame.empty:
                    last = frame.iloc[-1]
                    st.caption("Latest stored measurement: " + str(last["time"]) + " UTC · " + str(last["city"]))
                    t, h, pm = st.columns(3)
                    t.metric("Temperature", f"{last['temperature_c']:.1f} °C")
                    h.metric("Relative humidity", f"{last['humidity_pct']:.0f}%")
                    pm.metric("PM2.5", f"{last['pm2_5_ug_m3']:.1f} µg/m³")
            st.markdown("**Where to go next:** Open **Trends & flags** to explore changes, **Browse data** for daily and hourly tables, or **Report** for a downloadable explanation.")
            st.caption("Modeled environmental estimates. Statistical flags invite investigation; they are not confirmed incidents.")
    with tabs[1]:
        if result.get("plan"):
            st.json(result["plan"])
        else:
            st.info("Run the real pipeline to produce a plan.")
    with tabs[2]:
        st.caption("The exact program executed in the isolated staging worker.")
        if result.get("code"):
            st.code(result["code"], language="python")
        else:
            st.info("No generated program is available yet.")
    with tabs[3]:
        checks = result.get("validation_result", {}).get("checks", [])
        if checks:
            st.dataframe(checks, width="stretch", hide_index=True)
        else:
            st.info("No completed validation checks for this run.")
        if result.get("schema_drift", {}).get("detected"):
            st.json(result["schema_drift"])
        for repair in result.get("previous_fixes", []):
            st.write(f"**{repair['action']}**: {repair['diagnosis']}")
    with tabs[4]:
        analyses = result.get("anomalies", {})
        if analyses:
            metric = st.selectbox("Measurement", list(analyses))
            analysis = analyses[metric]
            st.write(f"{analysis['count']} flagged records · {analysis.get('samples', 0)} samples · {analysis['status']}")
            frame = preview(settings, "silver_environment", 5000)
            if not frame.empty:
                location_id = result.get("plan", {}).get("location_id")
                frame = frame[frame["location_id"] == location_id].sort_values("time")
                st.line_chart(frame, x="time", y=metric)
            st.dataframe(analysis.get("records", []), width="stretch", hide_index=True)
            st.caption(analysis.get("limitations", ""))
        else:
            st.info("Analysis runs only after validation and publication succeed.")
    with tabs[5]:
        if result.get("final_report"):
            st.markdown(result["final_report"])
            st.download_button("Download Markdown report", result["final_report"],
                               file_name=f"flowpilot-{result.get('run_id', 'report')}.md", mime="text/markdown")
        else:
            st.info("A report will be saved for every completed run, including failures.")
    with tabs[6]:
        table = st.selectbox("Warehouse layer", ("gold_daily_environment", "silver_environment"))
        try:
            frame = preview(settings, table)
            location = result.get("plan", {}).get("location_id")
            if location and "location_id" in frame.columns:
                frame = frame[frame["location_id"] == location]
            elif not location:
                frame = frame.iloc[0:0]
            st.dataframe(frame, width="stretch", hide_index=True)
        except Exception as error:
            st.info(f"Warehouse is temporarily busy: {error}")
        st.caption("Gold: local daily averages and completeness. Silver: canonical hourly data. Bronze: immutable JSON under data/bronze.")
        with st.expander("Read-only SQL explorer"):
            query = st.text_area("DuckDB SQL", "SELECT city, date, temperature_c, pm2_5_ug_m3, samples, complete_day FROM gold_daily_environment ORDER BY date DESC LIMIT 20")
            if st.button("Run read-only query"):
                try:
                    answer = run_sql(query, settings.db_path, read_only=True)
                    st.dataframe(pd.DataFrame(answer["rows"], columns=answer["columns"]), width="stretch", hide_index=True)
                except Exception as error:
                    st.error(str(error))
    with tabs[7]:
        try:
            st.dataframe(preview(settings, "_agent_runs"), width="stretch", hide_index=True)
            st.subheader("Schema changes")
            st.dataframe(preview(settings, "_agent_schema_events"), width="stretch", hide_index=True)
        except Exception as error:
            st.info(f"Warehouse is temporarily busy: {error}")
        if result.get("errors"):
            st.json(result["errors"])
