"""Manual/simulation trigger mode."""

from __future__ import annotations

import json
from pathlib import Path

import app.cli as cli
from app.adapters.devin_client import DevinSession
from app.config import load_settings
from app.core.orchestrator import Orchestrator
from app.store.sqlite_store import SQLiteRemediationStore
from tests.conftest import TEST_ENV, FakeDevinClient, FakeGitHubClient

SAMPLE_EVENT_PATH = Path(__file__).resolve().parent.parent / "samples" / "labeled_event.json"


def patch_cli(monkeypatch, orchestrator: Orchestrator) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: load_settings(dict(TEST_ENV)))
    monkeypatch.setattr(cli, "build_orchestrator", lambda settings: orchestrator)


def make_orchestrator(store: SQLiteRemediationStore) -> Orchestrator:
    return Orchestrator(
        FakeGitHubClient(), FakeDevinClient(), store, TEST_ENV["TARGET_REPO"]
    )


def test_run_command_starts_a_session(monkeypatch, capsys, store) -> None:
    orchestrator = make_orchestrator(store)
    patch_cli(monkeypatch, orchestrator)

    exit_code = cli.main(["run", "--issue", "101"])

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["issue_number"] == 101
    assert printed["trigger"] == "manual"
    assert len(store.list_runs()) == 1


def test_simulate_command_replays_sample_event(monkeypatch, capsys, store) -> None:
    orchestrator = make_orchestrator(store)
    patch_cli(monkeypatch, orchestrator)

    exit_code = cli.main(["simulate", "--event", str(SAMPLE_EVENT_PATH)])

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["trigger"] == "simulation"
    assert printed["issue_number"] == 101


def test_simulate_ignores_non_trigger_labels(monkeypatch, capsys, tmp_path, store) -> None:
    orchestrator = make_orchestrator(store)
    patch_cli(monkeypatch, orchestrator)
    event = json.loads(SAMPLE_EVENT_PATH.read_text())
    event["label"] = {"name": "documentation"}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))

    exit_code = cli.main(["simulate", "--event", str(event_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ignored"
    assert store.list_runs() == []


def test_status_command_prints_report(monkeypatch, capsys, store) -> None:
    orchestrator = make_orchestrator(store)
    patch_cli(monkeypatch, orchestrator)
    orchestrator.run_for_issue(101)
    capsys.readouterr()

    exit_code = cli.main(["status"])

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total"] == 1
    assert report["counts"]["running"] == 1


def test_watch_command_prints_until_terminal(monkeypatch, capsys, store) -> None:
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
    orchestrator = Orchestrator(
        FakeGitHubClient(), devin_client, store, TEST_ENV["TARGET_REPO"]
    )
    orchestrator.run_for_issue(101)
    capsys.readouterr()

    exit_code = cli.watch_runs(orchestrator, interval=0, sleep=lambda _: None)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "#101" in out
    assert "succeeded" in out
    assert "/pull/7" in out


def test_status_refresh_polls_devin(monkeypatch, capsys, store) -> None:
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
    orchestrator = Orchestrator(
        FakeGitHubClient(), devin_client, store, TEST_ENV["TARGET_REPO"]
    )
    patch_cli(monkeypatch, orchestrator)
    orchestrator.run_for_issue(101)
    capsys.readouterr()

    exit_code = cli.main(["status", "--refresh"])

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["counts"]["succeeded"] == 1
    assert report["runs"][0]["pr_url"].endswith("/pull/7")
