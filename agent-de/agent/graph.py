"""LangGraph pipeline with real tools, immutable raw snapshots, and bounded repairs."""
from datetime import datetime, timedelta, timezone
import json
import re
from pathlib import Path
import time
import uuid
from zoneinfo import ZoneInfo
import pandas as pd
from langgraph.graph import StateGraph, START, END
from agent.llm import LLMClient, make_client
from agent.prompts import SYSTEM_PROMPT, PLAN_PROMPT, CODE_SYSTEM, CODE_GEN_PROMPT, FIX_PROMPT, API_CATALOG
from agent.state import AgentState
from config import Settings
from pipeline.contracts import AIR, GEO, WEATHER, METRICS, default_plan, transform_code, validate_plan, reference_frame
from pipeline.events import EventLog, write_json
from pipeline.warehouse import initialize, publish, run_lock
from tools.api_tool import APITool
from tools.cache import digest
from tools.python_sandbox import SandboxPolicyError, code_fingerprint, run_python, validate_code
from tools.schema_tool import source_schema, expected_schema, compare_schema
from tools.validate_tool import validate_data
from tools.anomaly_tool import detect_anomalies
from tools.sql_tool import connection


def normalize_generated_code(code: str) -> str:
    """Accept a single Markdown code fence from compliant-but-chatty local models."""
    match = re.fullmatch(r"\s*```(?:python)?\s*\n(.*?)\n```\s*", code, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else code


class Pipeline:
    """One run with injectable LLM, HTTP, execution, and event sink dependencies."""
    def __init__(self, settings: Settings, *, client: LLMClient | None = None,
                 api=None, executor=run_python, on_event=None):
        self.settings = settings
        self.client = client or make_client(settings)
        self.api = api or APITool(settings)
        if settings.demo_mode:
            if settings.provider != 'builtin' or client is not None:
                raise ValueError('Free demo mode requires the built-in engine')
            from tools.demo_executor import run_trusted_transform
            self.executor = run_trusted_transform
        else:
            self.executor = executor
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.directory = settings.data_dir / "runs" / self.run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log = EventLog(settings.data_dir / "logs" / f"run_{self.run_id}.jsonl", self.run_id, on_event)
        self.options = {"numeric": False, "deduplicate": False, "aliases": {}}
        self.refresh = False
        self.started_at = datetime.now(timezone.utc)

    def model(self, system: str, payload: dict, *, json_mode: bool = True):
        label = "Built-in deterministic rules" if self.settings.provider == "builtin" else self.settings.provider
        with self.log.operation("llm", label, args={"task": payload["task"]}):
            text = self.client.complete(system, json.dumps(payload, default=str), json_mode=json_mode)
            return json.loads(text) if json_mode else text.strip()

    def plan(self, state: AgentState):
        last_error = ""
        for attempt in range(self.settings.max_retries + 1):
            try:
                proposal = self.model(SYSTEM_PROMPT, {"task": "plan", "instructions": PLAN_PROMPT,
                    "request": state["user_request"], "catalog": API_CATALOG,
                    "contract": default_plan(state["user_request"]), "previous_error": last_error})
                plan = validate_plan(proposal)
                break
            except (ValueError, RuntimeError) as error:
                last_error = str(error)
                if attempt == self.settings.max_retries:
                    raise
        from pipeline.cities import LOCATIONS
        with self.log.operation("api", "Resolve requested city", args={"city": plan["city"]}):
            catalog = next((value for name, value in LOCATIONS.items() if name.casefold() == plan["city"].casefold()), None)
            if catalog:
                location = dict(catalog)
            else:
                results = self.api.call_api(GEO, {"name": plan["city"], "count": 5, "language": "en", "format": "json"}).get("results", [])
                if not results:
                    raise ValueError("Geocoding found no matching city")
                location = results[0]
        ZoneInfo(location["timezone"])
        now = self.started_at
        plan.update({"city": location["name"], "location_id": str(location["id"]),
                     "latitude": location["latitude"], "longitude": location["longitude"],
                     "timezone": location["timezone"], "country": location.get("country", ""),
                     "as_of": (now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)).replace(tzinfo=None).isoformat(),
                     "window_start": (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=5)).replace(tzinfo=None).isoformat()})
        state["plan"] = plan
        return state

    def generate_code(self, state: AgentState):
        for attempt in range(self.settings.max_retries + 1):
            try:
                code = self.model(CODE_SYSTEM, {"task": "generate_code", "instructions": CODE_GEN_PROMPT,
                    "plan": state["plan"], "reference_code": transform_code(),
                    "previous_errors": state["errors"]}, json_mode=False)
                # Keep prose invalid; accept only a complete outer code fence.
                code = normalize_generated_code(code)
                validate_code(code)
                state["code"] = code
                return state
            except (ValueError, SyntaxError) as error:
                state["errors"].append(f"generate_code: {error}")
                if attempt == self.settings.max_retries:
                    raise

    def execute(self, state: AgentState):
        plan = state["plan"]
        params = {**plan["parameters"], "latitude": plan["latitude"], "longitude": plan["longitude"]}
        snapshots = {}
        with self.log.operation("api", "Fetch weather and air quality"):
            for name, url, fields in (("weather", WEATHER, "temperature_2m,relative_humidity_2m"), ("air", AIR, "pm2_5")):
                before = self.api.metrics.get("cache_hits", 0)
                with self.log.operation("cache", f"Check {name} response cache"):
                    with self.log.operation("sources", f"Read {name} from API broker", args={"url": url}):
                        snapshot = self.api.call_api(url, {**params, "hourly": fields}, refresh=self.refresh)
                hit = self.api.metrics.get("cache_hits", 0) > before
                self.log.emit("cache", "success", "Cache hit" if hit else "Fresh HTTP response", result={"source": name, "hit": hit})
                if not isinstance(snapshot.get("hourly"), dict) or "time" not in snapshot["hourly"]:
                    raise ValueError(f"{name}: missing hourly time series")
                expected_units = {"temperature_2m": ["°C", "C"], "relative_humidity_2m": ["%"]} if name == "weather" else {"pm2_5": ["μg/m³", "µg/m³", "ug/m3"]}
                for field, units in expected_units.items():
                    if field in snapshot["hourly"] and snapshot.get("hourly_units", {}).get(field) not in units:
                        raise ValueError(f"Unsupported or missing units for {field}")
                snapshots[name] = snapshot
                write_json(self.settings.data_dir / "bronze" / self.run_id / f"attempt_{state['retry_count']}_{name}.json",
                           {"url": url, "params": {**params, "hourly": fields}, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "sha256": digest(snapshot), "cache_hit": hit, "response": snapshot})
        self.refresh = False
        state["snapshots"] = snapshots
        state["source_schema"] = source_schema(snapshots)
        baseline = expected_schema(self.settings.db_path, "source:" + plan["location_id"])
        state["schema_drift"] = compare_schema(baseline, state["source_schema"]) if baseline else {"detected": False}
        self.log.emit("snapshots", "success", "Immutable raw responses archived", result={"sources": list(snapshots)})
        with self.log.operation("sandbox", "Apply trusted built-in transformation" if self.settings.demo_mode else "Execute generated program inside OS isolation"):
            result = self.executor(state["code"], settings=self.settings, snapshots=snapshots, plan=plan,
                                   attempt_dir=self.directory / f"attempt_{state['retry_count']}")
            state["execution_result"] = result
            if not result.get("success"):
                raise ValueError(result.get("error", "Execution failed"))
        self.log.emit("staging", "success", "Candidate table loaded in isolated staging database")
        return state

    def validate(self, state: AgentState):
        plan = state["plan"]
        with self.log.operation("metadata", "Compare candidate and accepted schemas"):
            baseline = expected_schema(self.settings.db_path, "target:" + plan["location_id"])
            result = validate_data("staged", Path(state["execution_result"]["db_path"]), plan=plan, expected=baseline)
            state["validation_result"] = result
            if not result["valid"]:
                failures = [x for x in result["checks"] if not x["passed"]]
                raise ValueError("Data-quality failure: " + json.dumps(failures, default=str)[:7000])
            if state["schema_drift"].get("detected") and not state.get("accepted_drift"):
                raise ValueError("Source schema drift requires an explicit repair decision")
        with connection(Path(state["execution_result"]["db_path"]), read_only=True) as con:
            frame = con.execute("SELECT * FROM staged").fetchdf()
        expected_frame = reference_frame(state["snapshots"], plan, self.options)
        try:
            pd.testing.assert_frame_equal(frame.sort_values(["location_id", "time"]).reset_index(drop=True),
                                          expected_frame, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-10)
        except AssertionError as error:
            state["validation_result"]["valid"] = False
            state["validation_result"]["checks"].append({"check": "source_reconciliation", "passed": False,
                                                       "detail": "Staged values do not match approved source measurements"})
            raise ValueError("Generated output failed source reconciliation") from error
        state["validation_result"]["checks"].append({"check": "source_reconciliation", "passed": True,
                                                   "detail": "Every staged value matches approved source measurements"})
        with self.log.operation("publish", "Publish validated hourly and daily tables atomically"):

            state["published"] = publish(self.settings, frame, plan, self.run_id,
                {"source:" + plan["location_id"]: state["source_schema"], "target:" + plan["location_id"]: result["schema"]},
                state["schema_drift"])
        self.log.emit("warehouse", "success", "Warehouse transaction committed", result=state["published"])
        return state

    def diagnose_and_fix(self, state: AgentState):
        if state["retry_count"] >= self.settings.max_retries:
            state["status"] = "failed"
            return state
        state["retry_count"] += 1
        self.log.retry_count = state["retry_count"]
        snapshots = state.get("snapshots", {})
        fields = snapshots.get("weather", {}).get("hourly", {})
        units = snapshots.get("weather", {}).get("hourly_units", {})
        before_options = json.dumps(self.options, sort_keys=True)
        for alias in ("temperature", "temperature_c", "temp_c"):
            if alias in fields and "temperature_2m" not in fields and units.get(alias) in {"°C", "C"}:
                self.options["aliases"][alias] = "temperature_2m"
        for key, kind in state.get("source_schema", {}).items():
            if key in {"weather.temperature_2m", "weather.relative_humidity_2m", "air.pm2_5"} and kind == "string":
                self.options["numeric"] = True
        checks = state.get("validation_result", {}).get("checks", [])
        if any(c["check"] == "unique_business_keys" and not c["passed"] for c in checks):
            self.options["deduplicate"] = True
        drift = state.get("schema_drift", {})
        accept_drift = bool(drift.get("detected"))
        changed = before_options != json.dumps(self.options, sort_keys=True)
        action = "transform" if changed else "accept_source_drift" if accept_drift and state.get("validation_result", {}).get("valid") else "refetch_once"
        if action == "refetch_once" and any(x["action"] == action for x in state["previous_fixes"]):
            raise ValueError("Source data is still invalid; no distinct safe repair remains")
        if action == "refetch_once":
            self.refresh = True
        diagnosis = {"transform": "Normalize verified aliases/numeric strings or remove identical duplicate keys",
                     "accept_source_drift": "Accept observed source drift after canonical output validation",
                     "refetch_once": "Refetch the source once without cache; never fabricate missing values"}[action]
        reference = transform_code(**self.options)
        answer = self.model(SYSTEM_PROMPT, {"task": "fix", "instructions": FIX_PROMPT,
            "code": state["code"], "error": state["errors"][-1], "validation_failures": state.get("validation_result", {}),
            "schema_diff": drift, "previous_fixes": state["previous_fixes"],
            "reference_code": reference, "diagnosis": diagnosis})
        code = answer["code"]
        validate_code(code)
        fingerprint = digest([code_fingerprint(code), action, drift])
        if any(x["fingerprint"] == fingerprint for x in state["previous_fixes"]):
            raise ValueError("Repeated repair rejected")
        if action == "transform" and code_fingerprint(code) == code_fingerprint(state["code"]):
            raise ValueError("Unchanged generated-code repair rejected")
        state["previous_fixes"].append({"fingerprint": fingerprint, "action": action, "diagnosis": str(answer["diagnosis"]), "code_hash": code_fingerprint(code)})
        state["code"] = code
        state["accepted_drift"] = accept_drift and action != "refetch_once"
        state["validation_result"] = {}
        state["status"] = "running"
        return state

    def anomaly_detect(self, state: AgentState):
        state["anomalies"] = {metric: detect_anomalies("silver_environment", metric, self.settings.db_path,
                                 location_id=state["plan"]["location_id"]) for metric in METRICS}
        state["status"] = "success"
        return state

    def report(self, state: AgentState):
        status = state.get("status", "failed")
        if status not in {"success", "partial"}:
            status = "partial" if state.get("published") else "failed"
        state["status"] = status
        plan = state.get("plan", {})
        lines = ["# FlowPilot — Real Pipeline Report", "", f"- Run: `{self.run_id}`", f"- Outcome: **{status}**",
                 f"- Request: {state['user_request']}", f"- Location: {plan.get('city', 'unresolved')} ({plan.get('country', '')})",
                 f"- Provider: {self.settings.provider}" + (" (deterministic rules, not an LLM)" if self.settings.provider == "builtin" else ""),
                 f"- Window: {plan.get('window_start', '?')} to {plan.get('as_of', '?')} UTC",
                 f"- Daily timezone: {plan.get('timezone', '?')}", f"- Repairs: {state['retry_count']}",
                 f"- Published: {json.dumps(state.get('published', {}))}", "", "## Validation"]
        for check in state.get("validation_result", {}).get("checks", []):
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {check['check']}: {check['detail']}")
        lines += ["", "## Repairs"] + [f"- {fix['action']}: {fix['diagnosis']}" for fix in state["previous_fixes"]]
        lines += ["", "## Anomalies"]
        for name, result in state.get("anomalies", {}).items():
            lines.append(f"- {name}: {result['count']} flags; {result['status']}; {result.get('samples', 0)} samples")
        lines += ["", "Statistical flags in modeled data are not confirmed incidents. Daily incomplete periods are labeled in the gold table.",
                  "", "## Errors encountered"] + ["- " + error for error in state["errors"]]
        lines += ["", "## Usage", json.dumps({"api": self.api.metrics, "provider": self.client.metrics}),
                  "", "## Source attribution", "Weather: [Open-Meteo](https://open-meteo.com/). Air quality: [CAMS / Copernicus Atmosphere Monitoring Service](https://atmosphere.copernicus.eu/) via [Open-Meteo](https://open-meteo.com/en/docs/air-quality-api).",
                  "", "These sources provide modeled estimates/forecasts, not direct sensor readings.",
                  "", f"Log: `{self.log.path}`", f"Raw snapshots: `{self.settings.data_dir / 'bronze' / self.run_id}`"]
        state["final_report"] = "\n".join(lines) + "\n"
        report_path = self.settings.data_dir / "reports" / f"{self.run_id}.md"
        report_path.write_text(state["final_report"])
        (self.directory / "pipeline.py").write_text(state.get("code", ""))
        state["step_history"] = self.log.events.copy()
        state["execution_result"] = state.get("execution_result", {})
        # Raw responses are already archived; keep result files compact.
        saved = {k: v for k, v in state.items() if k != "snapshots"}
        saved.update({"report_path": str(report_path), "log_path": str(self.log.path),
                      "metrics": {"api": self.api.metrics, "provider": self.client.metrics}})
        write_json(self.directory / "result.json", saved)
        write_json(self.settings.data_dir / "latest.json", saved)
        with connection(self.settings.db_path) as con:
            con.execute("INSERT INTO _agent_runs VALUES (?, ?, ?, ?, ?, ?)", [self.run_id, status,
                        self.started_at.replace(tzinfo=None), datetime.now(timezone.utc).replace(tzinfo=None),
                        state.get("published", {}).get("hourly_rows", 0), str(report_path)])
        return state

    def guarded(self, name, operation):
        def node(state):
            try:
                with self.log.operation(name, name.replace("_", " ")):
                    operation(state)
            except Exception as error:
                state["errors"].append(f"{name}: {type(error).__name__}: {error}")
                terminal = isinstance(error, (SandboxPolicyError, PermissionError))
                state["status"] = "needs_repair" if name in {"execute", "validate"} and not terminal else "failed"
            state["step_history"] = self.log.events.copy()
            return state
        return node

    def graph(self):
        graph = StateGraph(AgentState)
        for name in ("plan", "generate_code", "execute", "validate", "diagnose_and_fix", "anomaly_detect", "report"):
            graph.add_node(name, self.guarded(name, getattr(self, name)))
        graph.add_edge(START, "plan")
        graph.add_conditional_edges("plan", lambda s: "report" if s["status"] == "failed" else "generate_code")
        graph.add_conditional_edges("generate_code", lambda s: "report" if s["status"] == "failed" else "execute")
        graph.add_conditional_edges("execute", lambda s: "report" if s["status"] == "failed" else "diagnose_and_fix" if s["status"] == "needs_repair" else "validate")
        graph.add_conditional_edges("validate", lambda s: "report" if s["status"] == "failed" else "diagnose_and_fix" if s["status"] == "needs_repair" else "anomaly_detect")
        graph.add_conditional_edges("diagnose_and_fix", lambda s: "execute" if s["status"] == "running" else "report")
        graph.add_edge("anomaly_detect", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def run(self, request: str) -> dict:
        initial = AgentState(run_id=self.run_id, user_request=request, status="running", plan={}, code="",
                             retry_count=0, previous_fixes=[], errors=[], step_history=[], validation_result={},
                             anomalies={}, published={}, accepted_drift=False)
        with run_lock(self.settings):
            initialize(self.settings)
            self.log.emit("request", "success", request)
            self.log.emit("entry", "running", "Real pipeline started")
            self.log.emit("log", "running", "Writing structured JSONL events")
            state = self.graph().invoke(initial, config={"recursion_limit": 60})
            outcome = state.get("status", "failed")
            self.log.emit("log", "success", "Run log saved", metrics={"api": self.api.metrics, "provider": self.client.metrics})
            self.log.emit("entry", "success" if outcome == "success" else "failed", f"Pipeline {outcome}", outcome=outcome)
            state["step_history"] = self.log.events.copy()
            result_path = self.directory / "result.json"
            if result_path.exists():
                saved = json.loads(result_path.read_text())
                saved["step_history"] = state["step_history"]
                saved["status"] = outcome
                write_json(result_path, saved)
                write_json(self.settings.data_dir / "latest.json", saved)
            return state


def run_pipeline(request: str, settings: Settings | None = None, **kwargs) -> dict:
    """CLI/UI/test entry point; kwargs inject tools without changing graph behavior."""
    return Pipeline(settings or Settings.from_env(), **kwargs).run(request)
