"""SQLite-backed storage for job applications and discovered postings."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobhunt.models import Application, Posting, utc_now, validate_status

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
CREATE TABLE IF NOT EXISTS postings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    signature   TEXT NOT NULL,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    url         TEXT,
    location    TEXT,
    remote      INTEGER NOT NULL DEFAULT 0,
    salary      TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',
    posted_at   TEXT,
    description TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postings_signature ON postings(signature);
CREATE INDEX IF NOT EXISTS idx_postings_source ON postings(source);
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

    @staticmethod
    def _to_posting(row: sqlite3.Row) -> Posting:
        _, _, external_id = row["key"].partition(":")
        return Posting(
            source=row["source"],
            title=row["title"],
            company=row["company"],
            external_id=external_id or None,
            url=row["url"],
            location=row["location"],
            remote=bool(row["remote"]),
            salary=row["salary"],
            tags=tuple(json.loads(row["tags"] or "[]")),
            posted_at=row["posted_at"],
            description=row["description"],
            id=row["id"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )

    def upsert_posting(self, posting: Posting) -> tuple[Posting, bool]:
        """Store *posting*, de-duplicating against what is already known.

        A posting counts as a duplicate when either its per-source key or its
        company/title signature is already stored, so one role advertised on
        two boards is only reported once. Returns the stored posting and
        whether it was newly inserted.
        """
        now = utc_now()
        row = self._conn.execute(
            "SELECT id FROM postings WHERE key = ? OR signature = ? ORDER BY id LIMIT 1",
            (posting.key, posting.signature),
        ).fetchone()
        if row is not None:
            with self._conn:
                self._conn.execute(
                    "UPDATE postings SET last_seen = ? WHERE id = ?", (now, row["id"])
                )
            existing = self.get_posting(row["id"])
            assert existing is not None  # just matched by primary key
            return existing, False
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO postings
                    (key, signature, source, title, company, url, location, remote,
                     salary, tags, posted_at, description, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    posting.key,
                    posting.signature,
                    posting.source,
                    posting.title,
                    posting.company,
                    posting.url,
                    posting.location,
                    int(posting.remote),
                    posting.salary,
                    json.dumps(list(posting.tags)),
                    posting.posted_at,
                    posting.description,
                    now,
                    now,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        stored = self.get_posting(new_id)
        assert stored is not None  # just inserted
        return stored, True

    def get_posting(self, posting_id: int) -> Posting | None:
        """Return the posting with *posting_id*, or ``None``."""
        row = self._conn.execute("SELECT * FROM postings WHERE id = ?", (posting_id,)).fetchone()
        return self._to_posting(row) if row else None

    def list_postings(self, limit: int | None = None, source: str | None = None) -> list[Posting]:
        """Return known postings, most recently discovered first."""
        sql = "SELECT * FROM postings"
        params: list[object] = []
        if source is not None:
            sql += " WHERE source = ?"
            params.append(source)
        sql += " ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._to_posting(row) for row in rows]

    def count_postings(self) -> int:
        """Return how many postings have been recorded."""
        row = self._conn.execute("SELECT COUNT(*) AS n FROM postings").fetchone()
        return int(row["n"])
