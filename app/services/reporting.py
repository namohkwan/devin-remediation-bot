"""Presentation-friendly projections of remediation runs."""

from __future__ import annotations

from typing import Any

from app.store.models import RemediationRun, RunStatus


def serialize_run(run: RemediationRun) -> dict[str, Any]:
    """Convert a run into a JSON-serializable dictionary."""
    return {
        "id": run.id,
        "issue_number": run.issue_number,
        "issue_title": run.issue_title,
        "trigger": run.trigger,
        "session_id": run.session_id,
        "session_url": run.session_url,
        "status": run.status.value,
        "devin_status": run.devin_status,
        "pr_url": run.pr_url,
        "result": run.result,
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def build_dashboard_report(runs: list[RemediationRun]) -> dict[str, Any]:
    """Aggregate runs into the payload rendered by the dashboard."""
    counts = {status.value: 0 for status in RunStatus}
    for run in runs:
        counts[run.status.value] += 1
    return {
        "total": len(runs),
        "counts": counts,
        "runs": [serialize_run(run) for run in runs],
    }
