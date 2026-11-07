"""Render the architecture diagram using current component states."""

from pathlib import Path

import streamlit as st


DIAGRAM_PATH = (
    Path(__file__).resolve().parent / "docs" / "architecture.mmd"
)

# Internal event name -> Mermaid node ID and display label.
NODES = {
    "request": ("USER", "Plain-English request"),
    "entry": ("ENTRY", "CLI or Streamlit"),
    "plan": ("PLAN", "Plan and validate plan"),
    "llm": ("LLM", "LLM client"),
    "generate_code": ("CODE", "Generate Python code"),
    "execute": ("EXEC", "Execute attempt"),
    "api": ("API", "Allowlisted API broker"),
    "cache": ("CACHE", "API response cache"),
    "sources": ("SOURCES", "Open-Meteo APIs"),
    "snapshots": ("INPUT", "Approved response snapshots"),
    "sandbox": ("SANDBOX", "Isolated Python subprocess"),
    "staging": ("STAGE", "Attempt staging database"),
    "validate": ("VALIDATE", "Pandera and SQL validation"),
    "metadata": ("META", "Expected schemas and ownership"),
    "publish": ("PUBLISH", "Transactional publish"),
    "warehouse": ("DB", "Validated DuckDB warehouse"),
    "diagnose_and_fix": ("FIX", "Diagnose and repair"),
    "failure": ("FAILURE", "Failure report"),
    "anomaly_detect": ("ANOMALY", "Anomaly detection"),
    "report": ("REPORT", "Markdown report"),
    "log": ("LOG", "Structured run log"),
}

NODE_LABELS = {
    name: label
    for name, (_, label) in NODES.items()
}

ASSET_DIR = Path(__file__).resolve().parent / "ui_assets"

_FLOW = st.components.v2.component(
    "flowpilot.stable_architecture",
    html="""
      <div class="flow-shell">
        <div class="flow-legend" aria-label="Node status colors">
          <span style="--dot:#94a3b8">Pending</span>
          <span style="--dot:#60a5fa">Running</span>
          <span style="--dot:#4ade80">Completed</span>
          <span style="--dot:#fb923c">Repairing</span>
          <span style="--dot:#f87171">Failed</span>
        </div>
        <div class="flow-viewport">Preparing the architecture diagram…</div>
      </div>
    """,
    css=(ASSET_DIR / "flow.css").read_text(encoding="utf-8"),
    js=(ASSET_DIR / "flow.bundle.js").read_text(encoding="utf-8"),
)


def render_flow(statuses: dict[str, str]) -> None:
    """Mount one persistent SVG; subsequent events only transition its colors."""
    _FLOW(
        key="flowpilot_architecture",
        data={
            "diagram": DIAGRAM_PATH.read_text(encoding="utf-8"),
            "nodeIds": {name: value[0] for name, value in NODES.items()},
            "statuses": {
                name: status if status in {"pending", "running", "success", "failed"}
                else "pending"
                for name, status in statuses.items()
                if name in NODES
            },
        },
        width="stretch",
        height="content",
    )
