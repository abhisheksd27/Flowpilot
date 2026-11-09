"""CLI: run once, watch hourly or daily, install a local schedule, or inspect the warehouse."""
import argparse
from dataclasses import replace
import json
import logging
from config import DEFAULT_REQUEST, Settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="run", choices=("run", "watch", "schedule", "status", "preview"))
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--provider", choices=("builtin", "gemini", "groq", "ollama"))
    parser.add_argument("--frequency", choices=("hourly", "daily"), help="Schedule cadence (default hourly)")
    parser.add_argument("--at", help="Daily local time, HH:MM")
    parser.add_argument("--timezone", help="IANA timezone, default Asia/Kolkata")
    parser.add_argument("--run-now", action="store_true", help="Watch: also run immediately")
    parser.add_argument("--install", action="store_true", help="Schedule: install a per-user macOS launch agent")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Run: fetch fresh source responses instead of using API cache")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    overrides = {k: v for k, v in {"provider": args.provider, "schedule_time": args.at,
                                  "schedule_frequency": args.frequency, "schedule_timezone": args.timezone}.items() if v is not None}
    settings = replace(settings, **overrides)
    settings.prepare()
    try:
        if args.command == "run":
            from agent.graph import run_pipeline
            result = run_pipeline(args.request, settings, refresh=args.refresh)
            print(result.get("final_report", "Pipeline failed before reporting"))
            return 0 if result["status"] == "success" else 1
        if args.command == "preview":
            from pipeline.warehouse import preview
            print(preview(settings).to_string(index=False))
        else:
            from pipeline.scheduler import install_macos, next_run, scheduler_status, watch
            if args.command == "watch":
                watch(settings, args.request, run_now=args.run_now)
            elif args.command == "schedule" and args.install:
                print("Installed:", install_macos(settings, args.request))
                print("Next run:", next_run(settings).isoformat())
            else:
                print(json.dumps(scheduler_status(settings), indent=2))
                print("Next scheduled occurrence:", next_run(settings).isoformat())
        return 0
    except Exception as error:
        logging.exception("Pipeline command failed") if args.verbose else print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
