"""Fetchers for free, keyless job boards.

Each board exposes a public JSON endpoint that needs no API key and no
account, which keeps the whole search free and means nothing about you is
sent anywhere to *read* jobs.

Every parser takes an already-decoded JSON payload and returns
:class:`~jobhunt.models.Posting` objects. Fetching and parsing are kept
separate so the interesting logic is testable without touching the network.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from jobhunt.models import Posting

USER_AGENT = "jobhunt/0.1 (+https://github.com/MNB4556/job-hunt)"
TIMEOUT_SECONDS = 20

SOURCES: tuple[str, ...] = ("remotive", "arbeitnow", "remoteok", "hn")

REMOTIVE_URL = "https://remotive.com/api/remote-jobs?limit={limit}"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_URL = "https://remoteok.com/api"
HN_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# A HN header is usually "Company (Location) | Role | stack" or the same with
# dashes. Splitting on these separators recovers the useful fields.
_HN_SEPARATOR_RE = re.compile(r"\s*(?:\||\u2014|\u2013|\u00b7|\s-\s)\s*")
_HN_LOCATION_RE = re.compile(r"\(([^()]{2,60})\)")


class SourceError(RuntimeError):
    """Raised when a board cannot be reached or returns an unusable payload."""


def _get_json(url: str) -> Any:
    """Fetch *url* and decode the JSON body, wrapping failures in `SourceError`."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SourceError(f"could not fetch {url}: {exc}") from exc


def strip_html(markup: str | None) -> str:
    """Turn a fragment of HTML into one line of plain text."""
    if not markup:
        return ""
    text = _TAG_RE.sub(" ", markup)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _iso_from_epoch(value: Any) -> str | None:
    """Convert a Unix timestamp to an ISO-8601 UTC string, or ``None``."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC).replace(microsecond=0).isoformat()


def _salary_text(low: Any, high: Any) -> str | None:
    """Render a salary range from two numbers, or ``None`` when unknown."""
    minimum = low if isinstance(low, (int, float)) and low > 0 else None
    maximum = high if isinstance(high, (int, float)) and high > 0 else None
    if minimum and maximum:
        return f"{int(minimum)}-{int(maximum)}"
    if minimum:
        return f"{int(minimum)}+"
    if maximum:
        return f"up to {int(maximum)}"
    return None


def parse_remotive(payload: dict[str, Any]) -> list[Posting]:
    """Parse a Remotive ``/api/remote-jobs`` response."""
    postings = []
    for item in payload.get("jobs") or ():
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        if not title or not company:
            continue
        postings.append(
            Posting(
                source="remotive",
                external_id=str(item.get("id") or "") or None,
                title=title,
                company=company,
                url=item.get("url"),
                location=(item.get("candidate_required_location") or "").strip() or None,
                remote=True,  # Remotive only lists remote roles
                salary=(item.get("salary") or "").strip() or None,
                tags=tuple(item.get("tags") or ()),
                posted_at=item.get("publication_date"),
                description=strip_html(item.get("description")),
            )
        )
    return postings


def parse_arbeitnow(payload: dict[str, Any]) -> list[Posting]:
    """Parse an Arbeitnow job-board response."""
    postings = []
    for item in payload.get("data") or ():
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        if not title or not company:
            continue
        postings.append(
            Posting(
                source="arbeitnow",
                external_id=(item.get("slug") or "").strip() or None,
                title=title,
                company=company,
                url=item.get("url"),
                location=(item.get("location") or "").strip() or None,
                remote=bool(item.get("remote")),
                tags=tuple(item.get("tags") or ()) + tuple(item.get("job_types") or ()),
                posted_at=_iso_from_epoch(item.get("created_at")),
                description=strip_html(item.get("description")),
            )
        )
    return postings


def parse_remoteok(payload: list[Any]) -> list[Posting]:
    """Parse a Remote OK response.

    The first element of the array is a legal notice rather than a job, so
    entries without an ``id`` are skipped.
    """
    postings = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        title = (item.get("position") or "").strip()
        company = (item.get("company") or "").strip()
        if not title or not company:
            continue
        postings.append(
            Posting(
                source="remoteok",
                external_id=str(item.get("id")),
                title=title,
                company=company,
                url=item.get("url") or item.get("apply_url"),
                location=(item.get("location") or "").strip() or None,
                remote=True,  # Remote OK only lists remote roles
                salary=_salary_text(item.get("salary_min"), item.get("salary_max")),
                tags=tuple(item.get("tags") or ()),
                posted_at=item.get("date"),
                description=strip_html(item.get("description")),
            )
        )
    return postings


def parse_hn(payload: dict[str, Any]) -> list[Posting]:
    """Parse a Hacker News "Who is hiring?" thread on a best-effort basis.

    HN postings are free text, not structured data, so only the first line of
    each comment is used: it conventionally reads
    ``Company (Location) | Role | stack``. A comment that does not split into
    at least a company and a role is skipped, which drops the chatter that
    makes up most of those threads.
    """
    postings = []
    for item in payload.get("children") or ():
        if not isinstance(item, dict):
            continue
        raw = item.get("text") or ""
        if not raw:
            continue
        head = _WHITESPACE_RE.sub(" ", strip_html(raw.split("<p>", 1)[0]))
        if not head:
            continue
        segments = [segment.strip() for segment in _HN_SEPARATOR_RE.split(head) if segment.strip()]
        if len(segments) < 2:
            continue
        first = segments[0]
        location = None
        match = _HN_LOCATION_RE.search(first)
        if match:
            location = match.group(1).strip()
            first = (first[: match.start()] + first[match.end() :]).strip(" ,-")
        company = first
        role = segments[1]
        if not company or not role:
            continue
        postings.append(
            Posting(
                source="hn",
                external_id=str(item.get("id") or "") or None,
                title=role,
                company=company,
                url=f"https://news.ycombinator.com/item?id={item.get('id')}",
                location=location,
                remote="remote" in head.casefold(),
                posted_at=item.get("created_at"),
                description=strip_html(raw),
            )
        )
    return postings


PARSERS = {
    "remotive": parse_remotive,
    "arbeitnow": parse_arbeitnow,
    "remoteok": parse_remoteok,
    "hn": parse_hn,
}


def fetch_remotive(limit: int = 50) -> list[Posting]:
    """Fetch and parse Remotive postings."""
    payload = _get_json(REMOTIVE_URL.format(limit=limit))
    return parse_remotive(payload)[:limit]


def fetch_arbeitnow(limit: int = 50) -> list[Posting]:
    """Fetch and parse Arbeitnow postings."""
    payload = _get_json(ARBEITNOW_URL)
    return parse_arbeitnow(payload)[:limit]


def fetch_remoteok(limit: int = 50) -> list[Posting]:
    """Fetch and parse Remote OK postings (the board ignores limit parameters)."""
    payload = _get_json(REMOTEOK_URL)
    return parse_remoteok(payload)[:limit]


def fetch_hn(limit: int = 50) -> list[Posting]:
    """Fetch and parse the most recent "Who is hiring?" thread."""
    search = _get_json(HN_SEARCH_URL)
    story = next(
        (
            hit
            for hit in search.get("hits") or ()
            if re.search(r"who is hiring", hit.get("title") or "", re.IGNORECASE)
        ),
        None,
    )
    if story is None:
        raise SourceError("no 'Who is hiring?' thread found on Hacker News")
    payload = _get_json(HN_ITEM_URL.format(item_id=story["objectID"]))
    return parse_hn(payload)[:limit]


FETCHERS = {
    "remotive": fetch_remotive,
    "arbeitnow": fetch_arbeitnow,
    "remoteok": fetch_remoteok,
    "hn": fetch_hn,
}


def parse(source: str, payload: Any) -> list[Posting]:
    """Parse *payload* as if it came from *source*."""
    try:
        parser = PARSERS[source]
    except KeyError:
        raise ValueError(
            f"unknown source {source!r}; expected one of: {', '.join(SOURCES)}"
        ) from None
    return parser(payload)


def fetch(source: str, limit: int = 50) -> list[Posting]:
    """Fetch postings from a single named *source*."""
    try:
        fetcher = FETCHERS[source]
    except KeyError:
        raise ValueError(
            f"unknown source {source!r}; expected one of: {', '.join(SOURCES)}"
        ) from None
    return fetcher(limit)
