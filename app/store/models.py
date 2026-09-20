"""Domain models persisted by the store layer."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum


class RunStatus(str, Enum):
    """Lifecycle of a remediation run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (RunStatus.SUCCEEDED, RunStatus.FAILED)


TERMINAL_DEVIN_STATUSES = {"blocked", "stopped", "finished", "expired", "suspended"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RemediationRun:
    """A single attempt to remediate one GitHub issue."""

    issue_number: int
    issue_title: str
    trigger: str
    session_id: str | None = None
    session_url: str | None = None
    status: RunStatus = RunStatus.PENDING
    devin_status: str | None = None
    pr_url: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    id: int | None = None

    def touched(self, **changes: object) -> "RemediationRun":
        """Return a copy with ``changes`` applied and ``updated_at`` refreshed."""
        return replace(self, updated_at=utcnow(), **changes)  # type: ignore[arg-type]
