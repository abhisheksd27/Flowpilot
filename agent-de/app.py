"""Streamlit preview of the self-healing pipeline workflow."""

from collections.abc import Iterator
from datetime import datetime, timezone
import time
from typing import Any

import streamlit as st

from ui_results import render_results

from ui_flow import NODE_LABELS, render_flow


st.set_page_config(
    page_title="FlowPilot",
    page_icon="🔄",
    layout="wide",
)

MAX_RETRIES = 3

STAGES = NODE_LABELS

def new_view(request: str = "") -> dict[str, Any]:
    """Create the UI state for one simulation."""
    return {
        "request": request,
        "statuses": {node: "pending" for node in STAGES},
        "events": [],
        "retry_count": 0,
        "outcome": "idle",
    }


def make_event(
    node: str,
    status: str,
    message: str,
    retry_count: int,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Create one timestamped workflow event."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ),
        "node": node,
        "status": status,
        "message": message,
        "retry_count": retry_count,
        "outcome": outcome,
    }


def simulate_step(
    node: str,
    message: str,
    *,
    status: str = "success",
    retry_count: int = 0,
    outcome: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Emit start and finish events for one simulated operation."""
    yield make_event(
        node,
        "running",
        f"Starting simulated {STAGES[node].lower()}",
        retry_count,
    )

    # Deliberately slow the demo so its transitions are visible.
    time.sleep(0.7)

    yield make_event(
        node,
        status,
        message,
        retry_count,
        outcome,
    )

def simulate_pipeline(
    scenario: str,
) -> Iterator[dict[str, Any]]:
    """Simulate detailed events across the full architecture."""
    retry_count = 0

    def event(
        node: str,
        status: str,
        message: str,
    ) -> dict[str, Any]:
        """Create an event using the current repair counter."""
        return make_event(
            node,
            status,
            message,
            retry_count,
        )

    def step(
        node: str,
        message: str,
    ) -> Iterator[dict[str, Any]]:
        """Animate one simulated component operation."""
        yield from simulate_step(
            node,
            message,
            retry_count=retry_count,
        )

    yield event(
        "request",
        "success",
        "Demo request received.",
    )
    yield event(
        "entry",
        "running",
        "Frontend is displaying the simulation.",
    )
    yield event(
        "log",
        "running",
        "Collecting demo events in session memory.",
    )

    # Planning includes an LLM interaction.
    yield event("plan", "running", "Preparing the demo plan.")
    yield from step("llm", "Simulated planning response received.")
    yield event("plan", "success", "Demo plan accepted.")

    # Code generation includes another LLM interaction.
    yield event(
        "generate_code",
        "running",
        "Simulating code generation.",
    )
    yield from step("llm", "Simulated code response received.")
    yield event(
        "generate_code",
        "success",
        "Code-generation simulation completed; no code executed.",
    )

    while True:
        yield event(
            "execute",
            "running",
            f"Starting simulated attempt {retry_count + 1}.",
        )

        # API ingestion.
        yield event("api", "running", "Preparing approved requests.")

        yield from step(
            "cache",
            "Simulated cache lookup completed: cache miss.",
        )
        yield from step(
            "sources",
            "Simulated Open-Meteo response received.",
        )
        yield from step(
            "snapshots",
            "Simulated response snapshots prepared.",
        )

        yield event(
            "api",
            "success",
            "API ingestion simulation completed.",
        )

        # Isolated execution and staging.
        yield event(
            "sandbox",
            "running",
            "Simulating isolated Python execution.",
        )
        yield from step(
            "staging",
            "Simulated staging table prepared.",
        )
        yield event(
            "sandbox",
            "success",
            "Sandbox simulation completed.",
        )
        yield event(
            "execute",
            "success",
            "Execution simulation completed.",
        )

        # Validation checks the accepted schema metadata.
        yield event(
            "validate",
            "running",
            "Checking the simulated staged output.",
        )
        yield from step(
            "metadata",
            "Simulated expected-schema comparison completed.",
        )

        should_fail = (
            scenario == "Exhaust retries"
            or (
                scenario == "Recover after one failure"
                and retry_count == 0
            )
        )

        if should_fail:
            yield event(
                "validate",
                "failed",
                "Injected failure: duplicate business keys.",
            )

            if retry_count == MAX_RETRIES:
                outcome = "failed"
                break

            retry_count += 1

            yield event(
                "diagnose_and_fix",
                "running",
                f"Preparing simulated repair {retry_count}.",
            )
            yield from step(
                "llm",
                "Simulated diagnosis and repair response received.",
            )
            yield event(
                "diagnose_and_fix",
                "success",
                f"Simulated repair proposal {retry_count} prepared.",
            )

            continue

        yield event(
            "validate",
            "success",
            "Simulated validation passed.",
        )

        # Publishing remains active while data and metadata are updated.
        yield event(
            "publish",
            "running",
            "Simulating a warehouse transaction.",
        )
        yield from step(
            "warehouse",
            "Simulated warehouse update completed.",
        )
        yield from step(
            "metadata",
            "Simulated accepted-schema update completed.",
        )
        yield event(
            "publish",
            "success",
            "Simulated transaction completed; no database was written.",
        )

        yield from step(
            "anomaly_detect",
            "Simulated anomaly analysis completed.",
        )

        outcome = "success"
        break

    if outcome == "success":
        yield from step(
            "report",
            "Simulated success report prepared.",
        )
    else:
        yield from step(
            "failure",
            "Simulated failure report prepared: repair budget exhausted.",
        )

    yield event(
        "log",
        "success",
        "Demo event collection completed in session memory.",
    )

    yield make_event(
        "entry",
        "success",
        f"Frontend received the final outcome: {outcome}.",
        retry_count,
        outcome=outcome,
    )

def apply_event(event: dict[str, Any]) -> None:
    """Update component states and retain every event."""
    view = st.session_state["view"]

    if event["node"] == "execute" and event["status"] == "running":
        retry_components = (
            "api",
            "cache",
            "sources",
            "snapshots",
            "sandbox",
            "staging",
            "validate",
            "metadata",
        )

        for node in retry_components:
            view["statuses"][node] = "pending"

    view["statuses"][event["node"]] = event["status"]
    view["retry_count"] = event["retry_count"]
    view["events"].append(event)
    view["outcome"] = event["outcome"] or "running"

    st.session_state["view"] = view

def render_dashboard() -> None:
    """Keep the diagram's position and identity stable while events arrive."""
    view = st.session_state["view"]
    outcome_column, retry_column, event_column = st.columns(3)
    outcome_column.metric("Run outcome", view["outcome"].capitalize())
    retry_column.metric("Repairs attempted", f"{view['retry_count']} / {MAX_RETRIES}")
    event_column.metric("Events received", len(view["events"]))

    # Fixed geometry prevents multiline activity and terminal messages from
    # moving the diagram up and down as the run progresses.
    with st.container(height=100, border=False):
        active = [
            STAGES[node] for node, status in view["statuses"].items()
            if status == "running"
        ]
        if view["outcome"] == "success":
            st.success("Simulation completed successfully.")
        elif view["outcome"] == "failed":
            st.error("Simulation failed after three repairs. The failure report was prepared.")
        elif active:
            st.info("Active components: " + " · ".join(active))
        else:
            st.info("Ready to run the simulation.")

    st.subheader("Live pipeline architecture")
    render_flow(view["statuses"])

    st.subheader("Live event log")
    st.caption("Latest 20 events; full history remains in session state.")
    st.dataframe(view["events"][-20:], width="stretch", hide_index=True, height=280)


if "view" not in st.session_state:
    st.session_state["view"] = new_view()


st.title("FlowPilot")
st.caption("Self-healing data pipeline • Live workflow preview")

st.warning(
    "Simulation mode: no API calls, LLM calls, generated-code execution, "
    "or database writes occur."
)

request = st.text_area(
    "What should the pipeline do?",
    value=(
        "Track daily weather and air quality for Bengaluru "
        "and flag anomalies."
    ),
)

provider = st.selectbox(
    "LLM provider — preview selection only",
    ("ollama", "gemini", "groq"),
    help="No provider is contacted during the simulation.",
)

scenario = st.selectbox(
    "Simulation scenario",
    (
        "Success",
        "Recover after one failure",
        "Exhaust retries",
    ),
)

run_clicked = st.button(
    "Run simulation",
    type="primary",
    disabled=not request.strip(),
)

st.caption(
    "The request is displayed as context in this preview. "
    "Leave controls unchanged while the simulation runs."
)

if run_clicked:
    previous = st.session_state.pop("_flow_events", None)
    if previous is not None:
        previous.close()
    st.session_state["view"] = new_view(request.strip())
    st.session_state["view"]["outcome"] = "running"
    st.session_state["_flow_events"] = simulate_pipeline(scenario)


@st.fragment(run_every=0.2 if "_flow_events" in st.session_state else None)
def live_dashboard() -> None:
    """Advance one event per tick without reconstructing the surrounding page."""
    stream = st.session_state.get("_flow_events")
    finished = False
    if stream is not None:
        try:
            event = next(stream)
        except StopIteration:
            del st.session_state["_flow_events"]
            finished = True
        else:
            apply_event(event)
            if event["outcome"] is not None:
                stream.close()
                del st.session_state["_flow_events"]
                finished = True
    render_dashboard()
    if finished:
        # One final full rerun stops the fragment timer. The component keeps
        # the same key and DOM position, including across subsequent runs.
        st.rerun()


live_dashboard()
