"""Domain models for job applications."""

from __future__ import annotations

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
