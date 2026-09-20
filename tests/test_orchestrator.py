"""Orchestration logic with mocked adapters."""

from __future__ import annotations

from app.adapters.devin_client import DevinSession
from app.adapters.github_client import GitHubIssue
from app.core.orchestrator import Orchestrator
from app.store.models import RunStatus
from app.store.sqlite_store import SQLiteRemediationStore
from tests.conftest import FakeDevinClient, FakeGitHubClient

REPO = "namohkwan/superset"


def make_orchestrator(
    github_client: FakeGitHubClient,
    devin_client: FakeDevinClient,
    store: SQLiteRemediationStore,
) -> Orchestrator:
    return Orchestrator(github_client, devin_client, store, REPO)


def test_run_for_issue_calls_adapters_in_order_and_persists_run(
    github_client: FakeGitHubClient,
    devin_client: FakeDevinClient,
    store: SQLiteRemediationStore,
) -> None:
    orchestrator = make_orchestrator(github_client, devin_client, store)

    run = orchestrator.run_for_issue(101, trigger="manual")

    assert github_client.calls == [("get_issue", 101)]
    assert [name for name, _ in devin_client.calls] == ["create_session"]
    prompt = devin_client.calls[0][1]
    assert REPO in str(prompt)
    assert "Fix #101" in str(prompt)
    assert "structured_output" in str(prompt)

    assert run.status is RunStatus.RUNNING
    assert run.session_id == "devin-session-1"
    persisted = store.get(run.id or 0)
    assert persisted is not None
    assert persisted.trigger == "manual"
    assert persisted.issue_title == "Chart fails to render"


def test_github_is_called_before_devin(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    order: list[str] = []

    class RecordingGitHub(FakeGitHubClient):
        def get_issue(self, number: int) -> GitHubIssue:
            order.append("github")
            return super().get_issue(number)

    class RecordingDevin(FakeDevinClient):
        def create_session(self, prompt: str, idempotent: bool = True) -> DevinSession:
            order.append("devin")
            return super().create_session(prompt, idempotent)

    make_orchestrator(RecordingGitHub(), RecordingDevin(), store).run_for_issue(101)

    assert order == ["github", "devin"]


def test_run_for_issue_records_failure_when_devin_errors(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    devin_client = FakeDevinClient(create_error=RuntimeError("devin unavailable"))

    run = make_orchestrator(github_client, devin_client, store).run_for_issue(101)

    assert run.status is RunStatus.FAILED
    assert run.error == "devin unavailable"
    assert store.get(run.id or 0).status is RunStatus.FAILED


def test_refresh_run_marks_success_from_structured_output(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    devin_client = FakeDevinClient(
        poll_session=DevinSession(
            session_id="devin-session-1",
            status_enum="finished",
            structured_output={
                "pr_url": "https://github.com/namohkwan/superset/pull/7",
                "result": "pass",
            },
        )
    )
    orchestrator = make_orchestrator(github_client, devin_client, store)
    run = orchestrator.run_for_issue(101)

    refreshed = orchestrator.refresh_run(run)

    assert refreshed.status is RunStatus.SUCCEEDED
    assert refreshed.result == "pass"
    assert refreshed.pr_url.endswith("/pull/7")


def test_refresh_run_marks_failure_when_result_is_fail(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    devin_client = FakeDevinClient(
        poll_session=DevinSession(
            session_id="devin-session-1",
            status_enum="finished",
            structured_output={"pr_url": None, "result": "fail"},
        )
    )
    orchestrator = make_orchestrator(github_client, devin_client, store)

    refreshed = orchestrator.refresh_run(orchestrator.run_for_issue(101))

    assert refreshed.status is RunStatus.FAILED
    assert refreshed.result == "fail"


def test_refresh_run_keeps_blocked_sessions_open_and_records_pr(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    devin_client = FakeDevinClient(
        poll_session=DevinSession(
            session_id="devin-session-1",
            status_enum="blocked",
            pull_request_url="https://github.com/namohkwan/superset/pull/2",
        )
    )
    orchestrator = make_orchestrator(github_client, devin_client, store)

    refreshed = orchestrator.refresh_run(orchestrator.run_for_issue(101))

    assert refreshed.status is RunStatus.AWAITING_INPUT
    assert refreshed.status.is_terminal is False
    assert refreshed.pr_url.endswith("/pull/2")
    assert refreshed.result is None


def test_refresh_open_runs_skips_terminal_runs(
    github_client: FakeGitHubClient, store: SQLiteRemediationStore
) -> None:
    devin_client = FakeDevinClient(
        poll_session=DevinSession(
            session_id="devin-session-1",
            status_enum="finished",
            structured_output={"pr_url": "u", "result": "pass"},
        )
    )
    orchestrator = make_orchestrator(github_client, devin_client, store)
    orchestrator.run_for_issue(101)

    assert len(orchestrator.refresh_open_runs()) == 1
    assert orchestrator.refresh_open_runs() == []
