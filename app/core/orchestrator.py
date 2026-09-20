"""Orchestration shared by every trigger mode.

The orchestrator receives its adapters and store through constructor
injection, so the CLI (manual mode) and the webhook route execute exactly the
same logic against the same collaborators.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.adapters.devin_client import DevinClient, DevinSession
from app.adapters.github_client import GitHubClient
from app.config import Settings, get_settings
from app.core.prompts import build_remediation_prompt
from app.store.models import TERMINAL_DEVIN_STATUSES, RemediationRun, RunStatus
from app.store.sqlite_store import RemediationStore, SQLiteRemediationStore

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates GitHub, Devin, and persistence for one remediation run."""

    def __init__(
        self,
        github_client: GitHubClient,
        devin_client: DevinClient,
        store: RemediationStore,
        target_repo: str,
    ) -> None:
        self._github = github_client
        self._devin = devin_client
        self._store = store
        self._target_repo = target_repo

    @property
    def store(self) -> RemediationStore:
        return self._store

    def run_for_issue(self, issue_number: int, trigger: str = "manual") -> RemediationRun:
        """Fetch an issue, start a Devin session for it, and record the run."""
        logger.info("Starting remediation for issue #%s (trigger=%s)", issue_number, trigger)
        issue = self._github.get_issue(issue_number)
        prompt = build_remediation_prompt(issue, self._target_repo)

        run = RemediationRun(
            issue_number=issue.number,
            issue_title=issue.title,
            trigger=trigger,
        )
        run = self._store.add(run)

        try:
            session = self._devin.create_session(prompt)
        except Exception as exc:  # noqa: BLE001 - recorded and surfaced to the dashboard
            logger.exception("Failed to create Devin session for issue #%s", issue_number)
            failed = run.touched(status=RunStatus.FAILED, error=str(exc))
            return self._store.update(failed)

        started = run.touched(
            session_id=session.session_id,
            session_url=session.url,
            status=RunStatus.RUNNING,
            devin_status=session.status_enum,
        )
        logger.info("Devin session %s created for issue #%s", session.session_id, issue_number)
        return self._store.update(started)

    def refresh_run(self, run: RemediationRun) -> RemediationRun:
        """Poll Devin for ``run`` and persist any state transition."""
        if run.session_id is None or run.status.is_terminal:
            return run
        try:
            session = self._devin.get_session(run.session_id)
        except Exception as exc:  # noqa: BLE001 - transient polling errors are recorded
            logger.warning("Polling session %s failed: %s", run.session_id, exc)
            return self._store.update(run.touched(error=str(exc)))
        return self._store.update(self._apply_session(run, session))

    def refresh_open_runs(self) -> list[RemediationRun]:
        """Poll every non-terminal run."""
        return [self.refresh_run(run) for run in self._store.list_open_runs()]

    def list_runs(self, limit: int = 100) -> list[RemediationRun]:
        return self._store.list_runs(limit=limit)

    @staticmethod
    def _apply_session(run: RemediationRun, session: DevinSession) -> RemediationRun:
        output = session.structured_output or {}
        pr_url = output.get("pr_url") or run.pr_url
        result = output.get("result") or run.result
        status = run.status
        if session.status_enum in TERMINAL_DEVIN_STATUSES:
            status = RunStatus.SUCCEEDED if result == "pass" else RunStatus.FAILED
        elif session.status_enum:
            status = RunStatus.RUNNING
        return run.touched(
            devin_status=session.status_enum,
            session_url=session.url or run.session_url,
            pr_url=pr_url,
            result=result,
            status=status,
        )


def build_orchestrator(settings: Settings | None = None) -> Orchestrator:
    """Compose the production object graph from validated settings."""
    settings = settings or get_settings()
    github_client = GitHubClient(
        token=settings.github_token,
        repo=settings.target_repo,
        api_base=settings.github_api_base,
        timeout=settings.request_timeout_seconds,
    )
    devin_client = DevinClient(
        api_key=settings.devin_api_key,
        api_base=settings.devin_api_base,
        timeout=settings.request_timeout_seconds,
    )
    store = SQLiteRemediationStore(settings.database_path)
    return Orchestrator(github_client, devin_client, store, settings.target_repo)


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    """Return the process-wide orchestrator used by the API routers and CLI."""
    return build_orchestrator()
