"""SQLite-backed storage for job applications."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jobhunt.models import Application, utc_now, validate_status

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company     TEXT NOT NULL,
    role        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'saved',
    url         TEXT,
    source      TEXT,
    applied_on  TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);
"""

_COLUMNS = (
    "id",
    "company",
    "role",
    "status",
    "url",
    "source",
    "applied_on",
    "notes",
    "created_at",
    "updated_at",
)


class Store:
    """A tiny SQLite store for applications.

    The database file is the only place your job-search data lives, which is why
    it is gitignored: the tracker is safe to publish, your applications are not.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        parent = self.path.parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    @staticmethod
    def _to_application(row: sqlite3.Row) -> Application:
        return Application(**{column: row[column] for column in _COLUMNS})

    def add(self, application: Application) -> Application:
        """Insert *application* and return it with its assigned id and timestamps."""
        now = utc_now()
        created = application.created_at or now
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO applications
                    (company, role, status, url, source, applied_on, notes,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.company,
                    application.role,
                    application.status,
                    application.url,
                    application.source,
                    application.applied_on,
                    application.notes,
                    created,
                    now,
                ),
            )
        application.id = int(cursor.lastrowid or 0)
        application.created_at = created
        application.updated_at = now
        return application

    def get(self, application_id: int) -> Application | None:
        """Return the application with *application_id*, or ``None``."""
        row = self._conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return self._to_application(row) if row else None

    def list(self, status: str | None = None) -> list[Application]:
        """Return applications, optionally filtered by *status*, oldest first."""
        if status is None:
            rows = self._conn.execute("SELECT * FROM applications ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY id",
                (validate_status(status),),
            ).fetchall()
        return [self._to_application(row) for row in rows]

    def update_status(
        self, application_id: int, status: str, notes: str | None = None
    ) -> Application:
        """Move an application to *status*, raising ``KeyError`` if it does not exist."""
        assignments = ["status = ?", "updated_at = ?"]
        params: list[object] = [validate_status(status), utc_now()]
        if notes is not None:
            assignments.append("notes = ?")
            params.append(notes)
        params.append(application_id)
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE applications SET {', '.join(assignments)} WHERE id = ?",  # noqa: S608
                params,
            )
        if cursor.rowcount == 0:
            raise KeyError(f"no application with id {application_id}")
        updated = self.get(application_id)
        assert updated is not None  # guaranteed by the rowcount check above
        return updated

    def delete(self, application_id: int) -> bool:
        """Delete an application. Returns whether a row was removed."""
        with self._conn:
            cursor = self._conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        return cursor.rowcount > 0

    def stats(self) -> dict[str, int]:
        """Return a count per status plus a ``total``."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
        ).fetchall()
        counts = {row["status"]: row["n"] for row in rows}
        counts["total"] = sum(counts.values())
        return counts
