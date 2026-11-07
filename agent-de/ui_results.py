"""Result panels for the FlowPilot frontend demonstration."""

from typing import Any

import pandas as pd
import streamlit as st


def sample_data() -> pd.DataFrame:
    """Return fixed synthetic measurements, including one outlier."""
    return pd.DataFrame(
        {
            "date": pd.date_range(
                "2026-01-01", periods=14
            ).strftime("%Y-%m-%d"),
            "city": ["Bengaluru"] * 14,
            "temperature_c": [
                24, 25, 24, 26, 25, 24, 25,
                26, 24, 25, 24, 26, 25, 44,
            ],
            "humidity_pct": [
                60, 62, 61, 65, 63, 60, 64,
                62, 61, 63, 60, 64, 62, 61,
            ],
            "pm2_5_ug_m3": [
                18, 20, 19, 21, 20, 18, 22,
                19, 20, 21, 18, 19, 20, 23,
            ],
        }
    )


def score_temperature(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate illustrative anomaly scores on the synthetic data."""
    result = frame.copy()
    values = result["temperature_c"].astype(float)

    standard_deviation = values.std(ddof=0)

    if standard_deviation > 0:
        result["z_score"] = (
            values - values.mean()
        ) / standard_deviation
    else:
        result["z_score"] = 0.0

    result["z_flag"] = result["z_score"].abs() > 3

    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1

    if iqr > 0:
        result["iqr_flag"] = (
            (values < q1 - 1.5 * iqr)
            | (values > q3 + 1.5 * iqr)
        )
    else:
        result["iqr_flag"] = False

    return result


def build_report(
    view: dict[str, Any],
    row_count: int,
    flagged_count: int | None,
) -> str:
    """Build a Markdown report that clearly identifies simulated results."""
    failed_checks = sum(
        event["node"] == "validate"
        and event["status"] == "failed"
        for event in view["events"]
    )

    anomaly_summary = (
        f"{flagged_count} synthetic temperature outlier(s)"
        if flagged_count is not None
        else "Not run because validation did not succeed"
    )

    return "\n".join(
        [
            "# FlowPilot — Simulation Report",
            "",
            "> Demonstration only. No live source or LLM was called.",
            "",
            "## Request",
            "",
            view["request"],
            "",
            "## Run outcome",
            "",
            f"- Status: {view['outcome']}",
            f"- Preview provider: {view.get('provider', 'Not selected')}",
            f"- Repairs attempted: {view['retry_count']}",
            f"- Failed validation attempts: {failed_checks}",
            f"- Fixture rows displayed: {row_count}",
            "- Rows published to a warehouse: 0",
            "",
            "## Anomaly preview",
            "",
            anomaly_summary,
            "",
            "## Limitations",
            "",
            "- Measurements are a fixed synthetic Bengaluru dataset.",
            "- The request does not change the demonstration dataset.",
            "- Validation failure and repair events are scripted.",
            "- Statistical scores are calculated on synthetic values.",
            "- Displayed example code was not generated or executed.",
        ]
    )


def render_results(view: dict[str, Any]) -> None:
    """Display result tabs for a completed demonstration."""
    st.divider()
    st.subheader("Run results")

    if view["outcome"] not in {"success", "failed"}:
        st.info("Complete a simulation to explore its result panels.")
        return

    st.caption(
        "Demonstration fixtures only. These panels do not contain "
        "live API responses or warehouse records."
    )

    validation_events = [
        event
        for event in view["events"]
        if event["node"] == "validate"
        and event["status"] in {"success", "failed"}
    ]

    validation_failed = (
        bool(validation_events)
        and validation_events[-1]["status"] == "failed"
    )

    frame = sample_data()

    # Represent the rejected candidate when retries were exhausted.
    if validation_failed:
        frame = pd.concat(
            [frame, frame.iloc[[0]]],
            ignore_index=True,
        )

    analysis_ran = (
        view["statuses"]["anomaly_detect"] == "success"
    )

    scored = score_temperature(frame) if analysis_ran else None
    flagged = None

    if scored is not None:
        flagged = scored.loc[
            scored["z_flag"] | scored["iqr_flag"]
        ]

    report = build_report(
        view,
        row_count=len(frame),
        flagged_count=len(flagged) if flagged is not None else None,
    )

    tabs = st.tabs(
        [
            "Plan",
            "Generated Code",
            "Validation Results",
            "Anomalies",
            "Final Report",
            "Table Preview",
        ]
    )

    with tabs[0]:
        st.caption(
            "Fixed example plan; the request has not been interpreted "
            "by an LLM."
        )

        st.json(
            {
                "mode": "simulation",
                "request": view["request"],
                "provider": view.get("provider", "Not selected"),
                "location": "Bengaluru",
                "source": "Synthetic local fixture",
                "target_table": "daily_environment",
                "business_key": ["city", "date"],
                "transformations": [
                    "Align daily measurements",
                    "Remove duplicate business keys",
                ],
                "validation_rules": {
                    "missing_values": "Not allowed in this fixture",
                    "duplicate_keys": "Not allowed",
                    "temperature_c": [-60, 60],
                    "humidity_pct": [0, 100],
                    "pm2_5_ug_m3": "Nonnegative",
                },
                "schedule_suggestion": "Daily; not scheduled",
            }
        )

    with tabs[1]:
        st.info(
            "Hand-authored example only. This code was not generated "
            "by an LLM or executed by the simulation."
        )

        example_code = (
            "import pandas as pd\n\n"
            f"data = {sample_data().to_dict(orient='list')!r}\n\n"
            "frame = pd.DataFrame(data)\n"
            "frame = frame.drop_duplicates(subset=['city', 'date'])\n"
            "print(frame)\n"
        )

        st.code(example_code, language="python")

    with tabs[2]:
        st.caption(
            "These checks inspect the displayed fixture. "
            "Backend Pandera and SQL checks come later."
        )

        checks = {
            "No missing values": not frame.isna().any().any(),
            "Unique city/date keys": not frame.duplicated(
                subset=["city", "date"]
            ).any(),
            "Temperature within -60 to 60 C": frame[
                "temperature_c"
            ].between(-60, 60).all(),
            "Humidity within 0 to 100%": frame[
                "humidity_pct"
            ].between(0, 100).all(),
            "PM2.5 is nonnegative": frame[
                "pm2_5_ug_m3"
            ].ge(0).all(),
        }

        check_rows = [
            {
                "Check": name,
                "Result": "Passed" if passed else "Failed",
            }
            for name, passed in checks.items()
        ]

        st.dataframe(
            check_rows,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("**Validation attempt history**")
        st.dataframe(
            validation_events,
            use_container_width=True,
            hide_index=True,
        )

    with tabs[3]:
        if scored is None:
            st.warning(
                "Analysis was not run because validation failed."
            )
        else:
            st.caption(
                "Synthetic temperature series in Celsius. "
                "Scores use all 14 fixture values as their baseline."
            )

            st.line_chart(
                scored.set_index("date")[["temperature_c"]]
            )

            st.metric(
                "Flagged synthetic measurements",
                len(flagged),
            )

            st.dataframe(
                flagged[
                    [
                        "date",
                        "temperature_c",
                        "z_score",
                        "z_flag",
                        "iqr_flag",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Z-score threshold: absolute score > 3. "
                "IQR threshold: outside Q1 − 1.5×IQR or Q3 + 1.5×IQR."
            )

    with tabs[4]:
        st.markdown(report)

        st.download_button(
            label="Download Markdown report",
            data=report,
            file_name="flowpilot-demo-report.md",
            mime="text/markdown",
            key="download_demo_report",
        )

    with tabs[5]:
        if validation_failed:
            st.warning(
                "Rejected candidate fixture: includes a duplicate row. "
                "Nothing was published."
            )
        else:
            st.caption(
                "Synthetic candidate data. No database was written."
            )

        st.dataframe(
            frame,
            use_container_width=True,
            hide_index=True,
        )