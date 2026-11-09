"""Serializable state passed between LangGraph nodes."""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    user_request: str
    plan: dict[str, Any]
    code: str
    execution_result: dict[str, Any]
    validation_result: dict[str, Any]
    errors: list[str]
    retry_count: int
    step_history: list[dict[str, Any]]
    previous_fixes: list[dict[str, Any]]
    final_report: str
    status: str
    anomalies: dict[str, Any]
    published: dict[str, Any]
    snapshots: dict[str, Any]
    source_schema: dict[str, Any]
    schema_drift: dict[str, Any]
    accepted_drift: bool
    custom_rules: list[dict[str, Any]]
