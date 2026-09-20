"""Manual/simulation trigger mode.

Usage:
    python -m app.cli run --issue 123
    python -m app.cli simulate --event samples/labeled_event.json
    python -m app.cli status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.config import ConfigurationError, get_settings
from app.core.orchestrator import Orchestrator, build_orchestrator
from app.services.reporting import build_dashboard_report, serialize_run

logger = logging.getLogger("app.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Remediate a single issue")
    run_parser.add_argument("--issue", type=int, required=True, help="Issue number")

    simulate_parser = subparsers.add_parser(
        "simulate", help="Replay a saved GitHub issues event payload"
    )
    simulate_parser.add_argument(
        "--event", type=Path, required=True, help="Path to an issues event JSON file"
    )

    subparsers.add_parser("status", help="Print the current run report as JSON")
    return parser


def run_issue(orchestrator: Orchestrator, issue_number: int, trigger: str = "manual") -> int:
    run = orchestrator.run_for_issue(issue_number, trigger=trigger)
    print(json.dumps(serialize_run(run), indent=2))
    return 0 if run.error is None else 1


def simulate_event(orchestrator: Orchestrator, event_path: Path, trigger_label: str) -> int:
    payload = json.loads(event_path.read_text())
    action = payload.get("action")
    label_name = (payload.get("label") or {}).get("name")
    issue_number = (payload.get("issue") or {}).get("number")
    if action != "labeled" or label_name != trigger_label:
        print(json.dumps({"status": "ignored", "action": action, "label": label_name}, indent=2))
        return 0
    return run_issue(orchestrator, int(issue_number), trigger="simulation")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    orchestrator = build_orchestrator(settings)

    if args.command == "run":
        return run_issue(orchestrator, args.issue)
    if args.command == "simulate":
        return simulate_event(orchestrator, args.event, settings.trigger_label)
    if args.command == "status":
        report = build_dashboard_report(orchestrator.list_runs())
        print(json.dumps(report, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
