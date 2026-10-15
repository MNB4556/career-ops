"""Fetchers for free job boards.

Four of the five boards expose a public JSON endpoint that needs no API key
and no account, which keeps the search free and means nothing about you is
sent anywhere to *read* jobs. Adzuna - the one UK-native source, and the only
one carrying stated GBP salaries - needs a free key (see
:mod:`jobhunt.credentials`).

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
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from jobhunt.credentials import AdzunaCredentials, load_adzuna, redact
from jobhunt.models import Posting

USER_AGENT = "jobhunt/0.1 (+https://github.com/MNB4556/job-hunt)"
TIMEOUT_SECONDS = 20

SOURCES: tuple[str, ...] = ("adzuna", "remotive", "arbeitnow", "remoteok", "hn")

REMOTIVE_URL = "https://remotive.com/api/remote-jobs?limit={limit}"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_URL = "https://remoteok.com/api"
HN_SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
)
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"
# Adzuna is UK-only here: the "gb" market is where this is aimed.
ADZUNA_SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
ADZUNA_RESULTS_PER_PAGE = 50

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
# A HN header is usually "Company (Location) | Role | stack" or the same with
# dashes. Splitting on these separators recovers the useful fields.
_HN_SEPARATOR_RE = re.compile(r"\s*(?:\||\u2014|\u2013|\u00b7|\s-\s)\s*")
_HN_LOCATION_RE = re.compile(r"\(([^()]{2,60})\)")
# Posters sprinkle links through the header line, which otherwise end up as
# company or job titles.
_URL_RE = re.compile(
    r"https?://\S+|\bwww\.\S+|\b[\w-]+\.(?:com|io|dev|tech|org|net|ai|co|uk|app|xyz)\b\S*",
    re.IGNORECASE,
)


class SourceError(RuntimeError):
    """Raised when a board cannot be reached or returns an unusable payload."""


def _get_json(url: str) -> Any:
    """Fetch *url* and decode the JSON body, wrapping failures in `SourceError`."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SourceError(f"could not fetch {redact(url)}: {exc}") from exc


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


def _strip_urls(text: str) -> str:
    """Remove links, which posters sprinkle through HN header lines."""
    return _WHITESPACE_RE.sub(" ", _URL_RE.sub(" ", text)).strip(" ,-|")


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


def _int_or_none(value: Any) -> int | None:
    """Coerce a board's salary field to a positive int, or ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
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
        salary_min = _int_or_none(item.get("salary_min"))
        salary_max = _int_or_none(item.get("salary_max"))
        postings.append(
            Posting(
                source="remoteok",
                external_id=str(item.get("id")),
                title=title,
                company=company,
                url=item.get("url") or item.get("apply_url"),
                location=(item.get("location") or "").strip() or None,
                remote=True,  # Remote OK only lists remote roles
                salary=_salary_text(salary_min, salary_max),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency="USD" if (salary_min or salary_max) else None,
                tags=tuple(item.get("tags") or ()),
                posted_at=item.get("date"),
                description=strip_html(item.get("description")),
            )
        )
    return postings


def _adzuna_salary(item: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    """Return Adzuna's *stated* (minimum, maximum, currency).

    Adzuna estimates a salary for many ads. An estimate is not a stated
    figure, so predicted salaries are dropped rather than passed off as one.
    """
    if item.get("salary_is_predicted") in (1, "1", True):
        return None, None, None
    low = _int_or_none(item.get("salary_min"))
    high = _int_or_none(item.get("salary_max"))
    if low is None and high is None:
        return None, None, None
    return low, high, "GBP"


def _gbp_salary(low: int | None, high: int | None) -> str | None:
    """Render a stated GBP range for display, or ``None``."""
    if low and high and low == high:
        return f"£{low:,}"
    if low and high:
        return f"£{low:,}-£{high:,}"
    if low:
        return f"£{low:,}+"
    if high:
        return f"up to £{high:,}"
    return None


def _adzuna_location(item: dict[str, Any]) -> str | None:
    """Return the most specific location Adzuna offers for *item*."""
    location = item.get("location")
    if not isinstance(location, dict):
        return None
    display = (location.get("display_name") or "").strip()
    if display:
        return display
    areas = [str(area).strip() for area in location.get("area") or () if str(area).strip()]
    return ", ".join(areas) or None


def _adzuna_tags(item: dict[str, Any]) -> tuple[str, ...]:
    """Collect Adzuna's category and contract fields as tags."""
    tags: list[str] = []
    category = item.get("category")
    if isinstance(category, dict):
        for key in ("label", "tag"):
            value = category.get(key)
            if value:
                tags.append(str(value))
    for key in ("contract_time", "contract_type"):
        if item.get(key):
            tags.append(str(item[key]))
    return tuple(tags)


def parse_adzuna(payload: dict[str, Any]) -> list[Posting]:
    """Parse an Adzuna ``/v1/api/jobs/gb/search`` response."""
    postings = []
    for item in payload.get("results") or ():
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        company_field = item.get("company")
        company = (
            (company_field.get("display_name") or "").strip()
            if isinstance(company_field, dict)
            else ""
        )
        if not title or not company:
            continue
        location = _adzuna_location(item)
        salary_min, salary_max, salary_currency = _adzuna_salary(item)
        postings.append(
            Posting(
                source="adzuna",
                external_id=str(item.get("id") or "") or None,
                title=title,
                company=company,
                url=item.get("redirect_url"),
                location=location,
                remote=bool(re.search(r"\bremote\b", f"{title} {location or ''}", re.IGNORECASE)),
                salary=_gbp_salary(salary_min, salary_max),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=salary_currency,
                tags=_adzuna_tags(item),
                posted_at=item.get("created"),
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
        segments = [_strip_urls(segment) for segment in _HN_SEPARATOR_RE.split(head)]
        segments = [segment for segment in segments if segment]
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
    "adzuna": parse_adzuna,
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


def _adzuna_url(
    credentials: AdzunaCredentials, *, query: str | None, limit: int, page: int = 1
) -> str:
    """Build one Adzuna search URL.

    The result embeds the API key, so anything that logs it must first pass it
    through :func:`jobhunt.credentials.redact`.
    """
    params: dict[str, Any] = {
        "app_id": credentials.app_id,
        "app_key": credentials.app_key,
        "results_per_page": max(1, min(ADZUNA_RESULTS_PER_PAGE, limit)),
    }
    if query:
        params["what"] = query
    else:
        # No query given: stay in the IT category rather than paging through
        # the whole UK market.
        params["category"] = "it-jobs"
    return f"{ADZUNA_SEARCH_URL.format(page=page)}?{urlencode(params)}"


def fetch_adzuna(limit: int = 50, queries: Sequence[str] = ()) -> list[Posting]:
    """Fetch and parse Adzuna (UK) postings, one request per query.

    *limit* applies per query rather than to the combined result: truncating
    the union would let the first query crowd out the rest. Requests stay few
    regardless - the free tier allows 250 calls a day, and a daily digest built
    from a handful of targeted queries sits well inside that.
    """
    credentials = load_adzuna()
    if credentials is None:
        raise SourceError(
            "no Adzuna credentials: set ADZUNA_APP_ID and ADZUNA_APP_KEY, or write "
            "adzuna_app_id/adzuna_app_key to ~/.jobhunt/credentials.json"
        )
    wanted: tuple[str | None, ...] = tuple(
        query.strip() for query in queries if query and query.strip()
    ) or (None,)
    postings: list[Posting] = []
    seen: set[str] = set()
    for query in wanted:
        payload = _get_json(_adzuna_url(credentials, query=query, limit=limit))
        for posting in parse_adzuna(payload):
            if posting.key in seen:
                continue
            seen.add(posting.key)
            postings.append(posting)
    return postings


def parse(source: str, payload: Any) -> list[Posting]:
    """Parse *payload* as if it came from *source*."""
    try:
        parser = PARSERS[source]
    except KeyError:
        raise ValueError(
            f"unknown source {source!r}; expected one of: {', '.join(SOURCES)}"
        ) from None
    return parser(payload)


def fetch(source: str, limit: int = 50, queries: Sequence[str] = ()) -> list[Posting]:
    """Fetch postings from a single named *source*.

    *queries* applies only to Adzuna, which searches by phrase; every other
    board is fetched in full and filtered locally.
    """
    if source == "adzuna":
        return fetch_adzuna(limit, queries)
    try:
        fetcher = FETCHERS[source]
    except KeyError:
        raise ValueError(
            f"unknown source {source!r}; expected one of: {', '.join(SOURCES)}"
        ) from None
    return fetcher(limit)
