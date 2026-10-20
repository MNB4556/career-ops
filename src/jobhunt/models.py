"""Domain models for job applications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

STATUSES: tuple[str, ...] = (
    "saved",
    "applied",
    "screening",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
)

CLOSED_STATUSES: frozenset[str] = frozenset({"rejected", "withdrawn"})


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with second precision."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def today() -> str:
    """Return today's date in UTC as ``YYYY-MM-DD``."""
    return datetime.now(UTC).date().isoformat()


def days_since(moment: str | None) -> int | None:
    """Return whole days since *moment*, an ISO timestamp or date.

    ``None`` when *moment* is missing or unparseable: a hand-typed date should
    never be able to break a listing.
    """
    if not moment:
        return None
    try:
        then = datetime.fromisoformat(moment)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - then).days)


def validate_status(status: str) -> str:
    """Normalise *status*, raising ``ValueError`` if it is not a known status."""
    normalised = status.strip().lower()
    if normalised not in STATUSES:
        expected = ", ".join(STATUSES)
        raise ValueError(f"unknown status {status!r}; expected one of: {expected}")
    return normalised


@dataclass
class Application:
    """A single job application."""

    company: str
    role: str
    status: str = "saved"
    url: str | None = None
    source: str | None = None
    applied_on: str | None = None
    notes: str | None = None
    posting_id: int | None = None
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        self.company = self.company.strip()
        self.role = self.role.strip()
        if not self.company:
            raise ValueError("company must not be empty")
        if not self.role:
            raise ValueError("role must not be empty")
        self.status = validate_status(self.status)

    @property
    def is_closed(self) -> bool:
        """Whether this application is no longer in play."""
        return self.status in CLOSED_STATUSES


def normalise(value: str) -> str:
    """Collapse whitespace and casefold *value* so comparisons are stable."""
    return re.sub(r"\s+", " ", value).strip().casefold()


@dataclass
class Posting:
    """A job advert discovered on an external board.

    Postings are candidates, not applications: they arrive from a board, get
    filtered against your criteria, and only become an :class:`Application`
    when you decide to act on one.
    """

    source: str
    title: str
    company: str
    external_id: str | None = None
    url: str | None = None
    location: str | None = None
    remote: bool = False
    salary: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    tags: tuple[str, ...] = ()
    posted_at: str | None = None
    description: str | None = None
    id: int | None = None
    first_seen: str | None = None
    last_seen: str | None = None

    def __post_init__(self) -> None:
        self.source = self.source.strip().lower()
        self.title = self.title.strip()
        self.company = self.company.strip()
        if not self.source:
            raise ValueError("source must not be empty")
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.company:
            raise ValueError("company must not be empty")
        if self.salary_currency:
            self.salary_currency = self.salary_currency.strip().upper()
        self.tags = tuple(tag.strip() for tag in self.tags if tag and tag.strip())

    @property
    def key(self) -> str:
        """A stable identifier, unique within a source."""
        unique = self.external_id or self.url or f"{self.company}|{self.title}"
        return f"{self.source}:{unique}"

    @property
    def signature(self) -> str:
        """A content fingerprint used to spot one role across several boards."""
        return f"{normalise(self.company)}|{normalise(self.title)}"

    def to_application(self, status: str = "saved") -> Application:
        """Promote this posting into an application, keeping the link.

        The advert is the authoritative record of what you applied for, so the
        application remembers which posting it came from and can show it again.

        *status* exists because an advert is often recorded only once you have
        already applied to it, in which case it should be born ``applied``
        rather than passing through ``saved`` first.
        """
        return Application(
            company=self.company,
            role=self.title,
            status=status,
            url=self.url,
            source=self.source,
            posting_id=self.id,
        )


@dataclass
class Event:
    """One transition on an application, and when it happened.

    Keeping the transitions rather than only the current status is what makes
    "applied twelve days ago and heard nothing since" answerable at all.
    """

    application_id: int
    status: str
    note: str | None = None
    at: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self.status = validate_status(self.status)
