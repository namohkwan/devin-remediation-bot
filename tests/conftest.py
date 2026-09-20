"""Shared fixtures and fakes for the test suite."""

from __future__ import annotations

import pytest

from app.adapters.devin_client import DevinSession
from app.adapters.github_client import GitHubIssue
from app.store.sqlite_store import SQLiteRemediationStore

TEST_ENV = {
    "DEVIN_API_KEY": "test-devin-key",
    "GITHUB_TOKEN": "test-github-token",
    "GITHUB_WEBHOOK_SECRET": "test-webhook-secret",
    "TARGET_REPO": "namohkwan/superset",
}


class FakeGitHubClient:
    """Records calls and returns a canned issue."""

    def __init__(self, issue: GitHubIssue | None = None) -> None:
        self.issue = issue or GitHubIssue(
            number=101, title="Chart fails to render", body="Stack trace here"
        )
        self.calls: list[tuple[str, object]] = []

    def get_issue(self, number: int) -> GitHubIssue:
        self.calls.append(("get_issue", number))
        return self.issue


class FakeDevinClient:
    """Records calls and returns scripted sessions."""

    def __init__(
        self,
        session: DevinSession | None = None,
        poll_session: DevinSession | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.session = session or DevinSession(
            session_id="devin-session-1",
            status_enum="running",
            url="https://app.devin.ai/sessions/devin-session-1",
        )
        self.poll_session = poll_session
        self.create_error = create_error
        self.calls: list[tuple[str, object]] = []

    def create_session(self, prompt: str, idempotent: bool = True) -> DevinSession:
        self.calls.append(("create_session", prompt))
        if self.create_error is not None:
            raise self.create_error
        return self.session

    def get_session(self, session_id: str) -> DevinSession:
        self.calls.append(("get_session", session_id))
        return self.poll_session or self.session


@pytest.fixture()
def store() -> SQLiteRemediationStore:
    backend = SQLiteRemediationStore(":memory:")
    yield backend
    backend.close()


@pytest.fixture()
def github_client() -> FakeGitHubClient:
    return FakeGitHubClient()


@pytest.fixture()
def devin_client() -> FakeDevinClient:
    return FakeDevinClient()
