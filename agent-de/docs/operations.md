# Operations

```bash
python main.py run --provider builtin
python main.py preview
python main.py status
python main.py watch --frequency hourly --at 08:00 --timezone Asia/Kolkata
python main.py schedule --install --provider builtin --frequency hourly --at 08:00 --timezone Asia/Kolkata
```

The final command installs a macOS per-user LaunchAgent, `com.flowpilot.environment-pipeline`. It runs independently of Streamlit and starts at login. The computer must be awake and the external project drive mounted. An overdue scheduled execution catches up once after waking/restarting; it does not replay every missed day. The rolling fetch covers five prior days; longer outages require a separate backfill extension.

A single-daemon lock prevents duplicate schedulers; a warehouse lock serializes jobs. Setup/lock exceptions retry after 15 minutes. A completed pipeline failure is retained for review and the next normal daily run is scheduled. Inspect data/scheduler/status.json and ~/Library/Logs/FlowPilot/service.log and service.err.log.

Stop the macOS service:

```bash
launchctl bootout gui/$(id -u)/com.flowpilot.environment-pipeline
```

Remove its plist from ~/Library/LaunchAgents to prevent subsequent login startup. Linux users can supervise `main.py watch` with their process manager and Docker backend.

Artifacts: data/pipeline.duckdb, data/bronze, data/runs, data/logs, data/reports, data/latest.json. Back up the warehouse only when no writer is active. Retention is manual; snapshots and logs accumulate. Cache expiry is automatic, file cleanup is not. Rerunning an overlapping window updates matching business keys without duplicates. Never remove lock files while processes hold them.

Hourly is now the default local cadence, at minute 00 in Asia/Kolkata. Use `--frequency daily --at 08:00` to restore daily operation. See [cloud hosting](hosting.md) for the independent free hourly cloud pipeline and public dashboard.
