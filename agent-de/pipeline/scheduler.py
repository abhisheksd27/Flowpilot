"""Durable hourly/daily local scheduler with a single-daemon lock and macOS installation."""
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import threading
from zoneinfo import ZoneInfo
from config import DEFAULT_REQUEST, ROOT, Settings
from pipeline.events import write_json

LABEL = "com.flowpilot.environment-pipeline"


def next_run(settings: Settings, now: datetime | None = None) -> datetime:
    """Return the next configured local wall-clock occurrence as UTC."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(settings.schedule_timezone))
    if settings.schedule_frequency == "hourly":
        # Compute in UTC after rounding locally, preserving elapsed hours over DST.
        return local.replace(minute=0, second=0, microsecond=0).astimezone(timezone.utc) + timedelta(hours=1)
    hour, minute = map(int, settings.schedule_time.split(":"))
    scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if scheduled <= local:
        scheduled += timedelta(days=1)
    return scheduled.astimezone(timezone.utc)


def scheduler_status(settings: Settings) -> dict:
    """Return persisted heartbeat; label stale services rather than claiming they run."""
    path = settings.data_dir / "scheduler" / "status.json"
    if not path.exists():
        return {"status": "not_started"}
    state = json.loads(path.read_text())
    stamp = datetime.fromisoformat(state["heartbeat"])
    if (datetime.now(timezone.utc) - stamp).total_seconds() > 120 and state.get("status") != "running_pipeline":
        state["status"] = "stale_or_stopped"
    return state


def watch(settings: Settings, request: str = DEFAULT_REQUEST, *, run_now: bool = False) -> None:
    """Run on schedule while awake; after sleep/restart, catch up once instead of duplicating jobs."""
    from agent.graph import run_pipeline
    settings.prepare()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    folder = settings.data_dir / "scheduler"
    with (folder / "daemon.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A scheduler is already active") from None
        old = scheduler_status(settings)
        same_schedule = (old.get("frequency", "daily") == settings.schedule_frequency
                         and old.get("schedule") == settings.schedule_time
                         and old.get("timezone") == settings.schedule_timezone)
        due = (datetime.fromisoformat(old["next_run_utc"])
               if same_schedule and old.get("next_run_utc") else next_run(settings))
        if run_now:
            due = datetime.now(timezone.utc)
        state = {"status": "waiting", "pid": os.getpid(), "request": request,
                 "provider": settings.provider, "schedule": settings.schedule_time,
                 "frequency": settings.schedule_frequency,
                 "timezone": settings.schedule_timezone, "last_run": old.get("last_run")}
        while not stop.is_set():
            now = datetime.now(timezone.utc)
            state.update(heartbeat=now.isoformat(), next_run_utc=due.isoformat())
            if now >= due:
                state["status"] = "running_pipeline"
                write_json(folder / "status.json", state)
                try:
                    from dataclasses import replace
                    from pipeline.rules import load_config
                    from pipeline.cities import city_request
                    config = load_config(settings)
                    active_settings = replace(settings, schedule_frequency=config['frequency'], schedule_time=config['at']) if config else settings
                    active_request = city_request(config['city']) if config else request
                    result = run_pipeline(active_request, active_settings, refresh=True, incremental=True)
                    state["last_run"] = {"run_id": result["run_id"], "status": result["status"], "finished_at": datetime.now(timezone.utc).isoformat()}
                    state.pop('last_error', None)
                    if result['status'] != 'success':
                        state['last_error'] = '\n'.join(result.get('errors', []))
                    policy_path = settings.data_dir / 'retention-policy.json'
                    if policy_path.exists():
                        policy = json.loads(policy_path.read_text())
                        if policy.get('enabled'):
                            from pipeline.operations import apply_retention
                            apply_retention(settings, int(policy['days']))
                    due = next_run(active_settings)
                    state.update(request=active_request, frequency=active_settings.schedule_frequency, schedule=active_settings.schedule_time)
                except Exception as error:
                    state["last_error"] = str(error)
                    from pipeline.operations import alert
                    alert(settings, 'scheduler-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M'), str(error))
                    # A competing manual run or temporary setup error retries in 15 minutes.
                    due = datetime.now(timezone.utc) + timedelta(minutes=15)
                state["status"] = "waiting"
                state["next_run_utc"] = due.isoformat()
                state["heartbeat"] = datetime.now(timezone.utc).isoformat()
            write_json(folder / "status.json", state)
            try:
                from pipeline.operations import check_alerts
                from pipeline.contracts import default_plan
                check_alerts(settings, default_plan(state['request'])['city'])
            except Exception as error:
                import logging
                logging.getLogger(__name__).warning('Health check could not run: %s', error)
            stop.wait(15)
        state.update(status="stopped", heartbeat=datetime.now(timezone.utc).isoformat())
        write_json(folder / "status.json", state)


def install_macos(settings: Settings, request: str = DEFAULT_REQUEST) -> Path:
    """Install an explicitly requested per-user service; no root/system daemon."""
    if sys.platform != "darwin":
        raise RuntimeError("Use main.py watch under your process manager on Linux")
    settings.prepare()
    path = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
    path.parent.mkdir(parents=True, exist_ok=True)
    service_logs = Path.home() / "Library" / "Logs" / "FlowPilot"
    service_logs.mkdir(parents=True, exist_ok=True)
    arguments = [sys.executable, str(ROOT / "main.py"), "watch", "--provider", settings.provider,
                 "--request", request, "--frequency", settings.schedule_frequency, "--at", settings.schedule_time, "--timezone", settings.schedule_timezone]
    job = {"Label": LABEL, "ProgramArguments": arguments, "WorkingDirectory": str(Path.home()),
           "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 60,
           "EnvironmentVariables": {"DATA_DIR": str(settings.data_dir), "PYTHONUNBUFFERED": "1"},
           "StandardOutPath": str(service_logs / "service.log"),
           "StandardErrorPath": str(service_logs / "service.err.log")}
    if path.exists() and plistlib.loads(path.read_bytes()) != job:
        raise RuntimeError(f"A different service configuration already exists at {path}; stop it before replacing")
    path.write_bytes(plistlib.dumps(job))
    target = f"gui/{os.getuid()}"
    exists = subprocess.run(["launchctl", "print", f"{target}/{LABEL}"], capture_output=True).returncode == 0
    if not exists:
        subprocess.run(["launchctl", "bootstrap", target, str(path)], check=True)
    return path
