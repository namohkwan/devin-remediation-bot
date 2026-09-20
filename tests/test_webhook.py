"""Webhook trigger mode: HMAC verification and label filtering."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dashboard, webhook
from app.config import get_settings, load_settings
from app.core.orchestrator import Orchestrator, get_orchestrator
from app.store.sqlite_store import SQLiteRemediationStore
from tests.conftest import TEST_ENV, FakeDevinClient, FakeGitHubClient

SECRET = TEST_ENV["GITHUB_WEBHOOK_SECRET"]
SAMPLE_EVENT = json.loads(
    (Path(__file__).resolve().parent.parent / "samples" / "labeled_event.json").read_text()
)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def client(store: SQLiteRemediationStore) -> TestClient:
    github_client = FakeGitHubClient()
    devin_client = FakeDevinClient()
    orchestrator = Orchestrator(github_client, devin_client, store, TEST_ENV["TARGET_REPO"])

    app = FastAPI()
    app.include_router(webhook.router)
    app.include_router(dashboard.router)
    app.dependency_overrides[get_settings] = lambda: load_settings(dict(TEST_ENV))
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    with TestClient(app) as test_client:
        test_client.orchestrator = orchestrator  # type: ignore[attr-defined]
        yield test_client


def post_event(client: TestClient, payload: dict, signature: str | None = None) -> object:
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": signature if signature is not None else sign(body),
        "Content-Type": "application/json",
    }
    return client.post("/webhook", content=body, headers=headers)


def test_labeled_event_triggers_remediation(client: TestClient) -> None:
    response = post_event(client, SAMPLE_EVENT)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["run"]["trigger"] == "webhook"


def test_forged_signature_is_rejected(client: TestClient) -> None:
    response = post_event(client, SAMPLE_EVENT, signature="sha256=deadbeef")

    assert response.status_code == 401
    assert client.orchestrator.list_runs() == []  # type: ignore[attr-defined]


def test_missing_signature_is_rejected(client: TestClient) -> None:
    response = client.post("/webhook", json=SAMPLE_EVENT)

    assert response.status_code == 401


def test_other_labels_are_ignored(client: TestClient) -> None:
    payload = dict(SAMPLE_EVENT, label={"name": "documentation"})

    response = post_event(client, payload)

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert client.orchestrator.list_runs() == []  # type: ignore[attr-defined]


def test_status_page_renders_runs(client: TestClient) -> None:
    post_event(client, SAMPLE_EVENT)

    response = client.get("/status")

    assert response.status_code == 200
    assert "Devin Remediation Bot" in response.text
    assert "#101" in response.text


def test_poll_returns_json_report(client: TestClient) -> None:
    post_event(client, SAMPLE_EVENT)

    payload = client.get("/poll").json()

    assert payload["total"] == 1
    assert payload["runs"][0]["issue_number"] == 101
