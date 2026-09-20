"""SQLite-backed persistence behind a storage interface.

Higher layers depend on :class:`RemediationStore`, so the backend can be
replaced (Postgres, in-memory, ...) without touching other packages.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.store.models import RemediationRun, RunStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS remediation_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_number  INTEGER NOT NULL,
    issue_title   TEXT    NOT NULL,
    trigger       TEXT    NOT NULL,
    session_id    TEXT,
    session_url   TEXT,
    status        TEXT    NOT NULL,
    devin_status  TEXT,
    pr_url        TEXT,
    result        TEXT,
    error         TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
"""


class RemediationStore(ABC):
    """Storage interface used by the orchestration and service layers."""

    @abstractmethod
    def add(self, run: RemediationRun) -> RemediationRun:
        """Persist a new run and return it with its assigned id."""

    @abstractmethod
    def update(self, run: RemediationRun) -> RemediationRun:
        """Persist changes to an existing run."""

    @abstractmethod
    def get(self, run_id: int) -> RemediationRun | None:
        """Return a run by primary key."""

    @abstractmethod
    def get_by_session_id(self, session_id: str) -> RemediationRun | None:
        """Return the run tracking ``session_id``."""

    @abstractmethod
    def list_runs(self, limit: int = 100) -> list[RemediationRun]:
        """Return the most recent runs, newest first."""

    @abstractmethod
    def list_open_runs(self) -> list[RemediationRun]:
        """Return runs that have not reached a terminal state."""

    @abstractmethod
    def delete_all(self) -> None:
        """Remove every run (used by tests and local resets)."""


class SQLiteRemediationStore(RemediationStore):
    """Concrete SQLite implementation of :class:`RemediationStore`."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def add(self, run: RemediationRun) -> RemediationRun:
        cursor = self._connection.execute(
            """
            INSERT INTO remediation_runs (
                issue_number, issue_title, trigger, session_id, session_url,
                status, devin_status, pr_url, result, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._to_row(run),
        )
        self._connection.commit()
        run.id = int(cursor.lastrowid)
        return run

    def update(self, run: RemediationRun) -> RemediationRun:
        if run.id is None:
            raise ValueError("Cannot update a run that has not been persisted yet")
        self._connection.execute(
            """
            UPDATE remediation_runs SET
                issue_number = ?, issue_title = ?, trigger = ?, session_id = ?,
                session_url = ?, status = ?, devin_status = ?, pr_url = ?,
                result = ?, error = ?, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (*self._to_row(run), run.id),
        )
        self._connection.commit()
        return run

    def get(self, run_id: int) -> RemediationRun | None:
        row = self._connection.execute(
            "SELECT * FROM remediation_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def get_by_session_id(self, session_id: str) -> RemediationRun | None:
        row = self._connection.execute(
            "SELECT * FROM remediation_runs WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._from_row(row) if row else None

    def list_runs(self, limit: int = 100) -> list[RemediationRun]:
        rows = self._connection.execute(
            "SELECT * FROM remediation_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return self._from_rows(rows)

    def list_open_runs(self) -> list[RemediationRun]:
        rows = self._connection.execute(
            "SELECT * FROM remediation_runs WHERE status IN (?, ?) ORDER BY id ASC",
            (RunStatus.PENDING.value, RunStatus.RUNNING.value),
        ).fetchall()
        return self._from_rows(rows)

    def delete_all(self) -> None:
        self._connection.execute("DELETE FROM remediation_runs")
        self._connection.commit()

    @staticmethod
    def _to_row(run: RemediationRun) -> tuple[object, ...]:
        return (
            run.issue_number,
            run.issue_title,
            run.trigger,
            run.session_id,
            run.session_url,
            run.status.value,
            run.devin_status,
            run.pr_url,
            run.result,
            run.error,
            run.created_at.isoformat(),
            run.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RemediationRun:
        return RemediationRun(
            id=row["id"],
            issue_number=row["issue_number"],
            issue_title=row["issue_title"],
            trigger=row["trigger"],
            session_id=row["session_id"],
            session_url=row["session_url"],
            status=RunStatus(row["status"]),
            devin_status=row["devin_status"],
            pr_url=row["pr_url"],
            result=row["result"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @classmethod
    def _from_rows(cls, rows: Iterable[sqlite3.Row]) -> list[RemediationRun]:
        return [cls._from_row(row) for row in rows]
