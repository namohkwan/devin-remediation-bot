"""CRUD behaviour of the SQLite store."""

from __future__ import annotations

from app.store.models import RemediationRun, RunStatus
from app.store.sqlite_store import SQLiteRemediationStore


def make_run(issue_number: int = 101, **kwargs: object) -> RemediationRun:
    return RemediationRun(
        issue_number=issue_number,
        issue_title=f"Issue {issue_number}",
        trigger="manual",
        **kwargs,  # type: ignore[arg-type]
    )


def test_add_assigns_id_and_get_round_trips(store: SQLiteRemediationStore) -> None:
    run = store.add(make_run())

    assert run.id is not None
    fetched = store.get(run.id)
    assert fetched is not None
    assert fetched.issue_number == 101
    assert fetched.status is RunStatus.PENDING


def test_update_persists_changes(store: SQLiteRemediationStore) -> None:
    run = store.add(make_run())

    store.update(
        run.touched(
            session_id="sess-1",
            status=RunStatus.SUCCEEDED,
            pr_url="https://github.com/namohkwan/superset/pull/7",
            result="pass",
        )
    )

    fetched = store.get(run.id or 0)
    assert fetched is not None
    assert fetched.status is RunStatus.SUCCEEDED
    assert fetched.pr_url.endswith("/pull/7")
    assert fetched.result == "pass"


def test_get_by_session_id(store: SQLiteRemediationStore) -> None:
    run = store.add(make_run())
    store.update(run.touched(session_id="sess-42", status=RunStatus.RUNNING))

    found = store.get_by_session_id("sess-42")

    assert found is not None
    assert found.issue_number == 101
    assert store.get_by_session_id("unknown") is None


def test_list_runs_is_newest_first_and_open_runs_excludes_terminal(
    store: SQLiteRemediationStore,
) -> None:
    first = store.add(make_run(1))
    second = store.add(make_run(2))
    store.update(second.touched(status=RunStatus.SUCCEEDED))
    store.update(first.touched(status=RunStatus.RUNNING))

    assert [run.issue_number for run in store.list_runs()] == [2, 1]
    assert [run.issue_number for run in store.list_open_runs()] == [1]


def test_delete_all(store: SQLiteRemediationStore) -> None:
    store.add(make_run())

    store.delete_all()

    assert store.list_runs() == []
