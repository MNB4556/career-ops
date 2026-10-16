"""SQLite-backed storage for job applications and discovered postings."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jobhunt.models import (
    CLOSED_STATUSES,
    Application,
    Event,
    Posting,
    today,
    utc_now,
    validate_status,
)

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
    posting_id  INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);
CREATE INDEX IF NOT EXISTS idx_applications_posting ON applications(posting_id);
CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    status         TEXT NOT NULL,
    note           TEXT,
    at             TEXT NOT NULL,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_events_application ON events(application_id);
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
    salary_min  INTEGER,
    salary_max  INTEGER,
    salary_currency TEXT,
    tags        TEXT NOT NULL DEFAULT '[]',
    posted_at   TEXT,
    description TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postings_signature ON postings(signature);
CREATE INDEX IF NOT EXISTS idx_postings_source ON postings(source);
"""

# Columns added after the first release. Existing databases are upgraded in
# place rather than being thrown away.
_ADDED_COLUMNS = {
    "postings": (
        ("salary_min", "INTEGER"),
        ("salary_max", "INTEGER"),
        ("salary_currency", "TEXT"),
    ),
    "applications": (("posting_id", "INTEGER"),),
}

_COLUMNS = (
    "id",
    "company",
    "role",
    "status",
    "url",
    "source",
    "applied_on",
    "notes",
    "posting_id",
    "created_at",
    "updated_at",
)

_EVENT_COLUMNS = ("id", "application_id", "status", "note", "at")


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
        # Without this, deleting an application would leave its history behind.
        self._conn.execute("PRAGMA foreign_keys = ON")
        # Upgrade existing tables before applying the schema. The schema's
        # indexes may cover a column that a database from an earlier release
        # only gains in the migration, and creating that index first fails.
        self._migrate()
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def _migrate(self) -> None:
        """Add columns introduced after this database was created, in place."""
        present = {
            row["name"]
            for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table, columns in _ADDED_COLUMNS.items():
            if table not in present:
                continue  # the schema is about to create it, with every column
            existing = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
            }
            for column, kind in columns:
                if column not in existing:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {kind}"  # noqa: S608
                    )

    @staticmethod
    def _to_application(row: sqlite3.Row) -> Application:
        return Application(**{column: row[column] for column in _COLUMNS})

    def add(self, application: Application) -> Application:
        """Insert *application*, returning it with its id, stamps and first event."""
        now = utc_now()
        created = application.created_at or now
        applied_on = application.applied_on
        if applied_on is None and application.status == "applied":
            applied_on = today()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO applications
                    (company, role, status, url, source, applied_on, notes,
                     posting_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.company,
                    application.role,
                    application.status,
                    application.url,
                    application.source,
                    applied_on,
                    application.notes,
                    application.posting_id,
                    created,
                    now,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
            self._record_event(new_id, application.status, application.notes, created)
        application.id = new_id
        application.applied_on = applied_on
        application.created_at = created
        application.updated_at = now
        return application

    def _record_event(self, application_id: int, status: str, note: str | None, at: str) -> None:
        """Append one transition to an application's history."""
        self._conn.execute(
            "INSERT INTO events (application_id, status, note, at) VALUES (?, ?, ?, ?)",
            (application_id, status, note, at),
        )

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
        """Move an application to *status*, recording the transition.

        The first move to ``applied`` also stamps ``applied_on``: that date is
        what a follow-up is measured from, and it should not depend on
        remembering to pass it. Raises ``KeyError`` for an unknown id.
        """
        status = validate_status(status)
        existing = self.get(application_id)
        if existing is None:
            raise KeyError(f"no application with id {application_id}")
        now = utc_now()
        assignments = ["status = ?", "updated_at = ?"]
        params: list[object] = [status, now]
        if notes is not None:
            assignments.append("notes = ?")
            params.append(notes)
        if status == "applied" and not existing.applied_on:
            assignments.append("applied_on = ?")
            params.append(today())
        params.append(application_id)
        with self._conn:
            self._conn.execute(
                f"UPDATE applications SET {', '.join(assignments)} WHERE id = ?",  # noqa: S608
                params,
            )
            self._record_event(application_id, status, notes, now)
        updated = self.get(application_id)
        assert updated is not None  # guaranteed by the existence check above
        return updated

    def delete(self, application_id: int) -> bool:
        """Delete an application and its history. Returns whether a row was removed."""
        with self._conn:
            cursor = self._conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        return cursor.rowcount > 0

    def find_by_posting(self, posting_id: int) -> Application | None:
        """Return the application already tracking *posting_id*, if any.

        Saving the same advert twice should not produce two applications.
        """
        row = self._conn.execute(
            "SELECT * FROM applications WHERE posting_id = ? ORDER BY id LIMIT 1",
            (posting_id,),
        ).fetchone()
        return self._to_application(row) if row else None

    def list_open(self) -> list[Application]:
        """Return applications still in play, oldest first.

        Rejected and withdrawn are the only statuses that need no follow-up;
        an unanswered offer still does.
        """
        placeholders = ", ".join("?" for _ in CLOSED_STATUSES)
        rows = self._conn.execute(
            f"SELECT * FROM applications WHERE status NOT IN ({placeholders}) ORDER BY id",  # noqa: S608
            tuple(sorted(CLOSED_STATUSES)),
        ).fetchall()
        return [self._to_application(row) for row in rows]

    def timeline(self, application_id: int) -> list[Event]:
        """Return the recorded transitions for an application, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM events WHERE application_id = ? ORDER BY id", (application_id,)
        ).fetchall()
        return [Event(**{column: row[column] for column in _EVENT_COLUMNS}) for row in rows]

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
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"],
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
                     salary, salary_min, salary_max, salary_currency,
                     tags, posted_at, description, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    posting.salary_min,
                    posting.salary_max,
                    posting.salary_currency,
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
