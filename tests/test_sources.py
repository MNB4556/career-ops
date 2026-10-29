"""Tests for the job-board parsers and the HTML helpers."""

from __future__ import annotations

import urllib.error
from typing import Any

import pytest

from jobhunt.sources import (
    PARSERS,
    SOURCES,
    SourceError,
    _get_json,
    fetch_adzuna,
    parse,
    parse_adzuna,
    parse_arbeitnow,
    parse_hn,
    parse_remoteok,
    parse_remotive,
    strip_html,
)

REMOTIVE_PAYLOAD: dict[str, Any] = {
    "job-count": 1,
    "jobs": [
        {
            "id": 1680495,
            "url": "https://remotive.com/remote-jobs/dev/backend-1680495",
            "title": "Backend Engineer",
            "company_name": "Acme",
            "tags": ["python", "django"],
            "candidate_required_location": "Worldwide",
            "publication_date": "2026-10-11T20:17:27",
            "salary": "$60k",
            "description": "<p>Build <b>things</b> with Python</p><ul><li>Remote</li></ul>",
        }
    ],
}

ARBEITNOW_PAYLOAD: dict[str, Any] = {
    "data": [
        {
            "slug": "backend-engineer-berlin-1",
            "company_name": "Beta GmbH",
            "title": "Backend Engineer (m/w/d)",
            "description": "<h2>Start</h2>",
            "remote": False,
            "url": "https://www.arbeitnow.com/jobs/beta/backend-engineer-berlin-1",
            "tags": ["Software Development"],
            "job_types": ["permanent"],
            "location": "Berlin",
            "created_at": 1792101645,
        }
    ]
}

REMOTEOK_PAYLOAD: list[Any] = [
    {"last_updated": 1792080021, "legal": "Please link back to Remote OK."},
    {
        "id": "1137514",
        "slug": "backend-engineer-acme-1137514",
        "company": "Acme",
        "position": "Backend Engineer",
        "tags": ["python"],
        "description": "<p>Remote role</p>",
        "location": "",
        "url": "https://remoteok.com/remote-jobs/backend-engineer-acme-1137514",
        "salary_min": 60000,
        "salary_max": 90000,
        "date": "2026-10-14T16:00:05+00:00",
    },
]

HN_PAYLOAD: dict[str, Any] = {
    "id": 49922569,
    "children": [
        {
            "id": 1,
            "text": (
                "PrairieLearn (Remote US) - Full-Stack Software Engineer - TypeScript / React"
                "<p>We build an assessment platform.</p>"
            ),
            "created_at": "2026-10-01T15:02:37.000Z",
        },
        {"id": 2, "text": "Congratulations, nice launch!<p>Really cool.</p>"},
        {"id": 3, "text": ""},
        "not-a-dict",
    ],
}


def test_parse_remotive_maps_fields():
    (posting,) = parse_remotive(REMOTIVE_PAYLOAD)
    assert posting.source == "remotive"
    assert posting.company == "Acme"
    assert posting.title == "Backend Engineer"
    assert posting.remote is True
    assert posting.location == "Worldwide"
    assert posting.tags == ("python", "django")
    assert posting.external_id == "1680495"


def test_parse_remotive_strips_html_from_description():
    (posting,) = parse_remotive(REMOTIVE_PAYLOAD)
    assert posting.description == "Build things with Python Remote"


def test_parse_remotive_skips_incomplete_entries():
    payload = {"jobs": [{"id": 1, "title": "", "company_name": "Acme"}]}
    assert parse_remotive(payload) == []


def test_parse_arbeitnow_converts_timestamp_and_tags():
    (posting,) = parse_arbeitnow(ARBEITNOW_PAYLOAD)
    assert posting.company == "Beta GmbH"
    assert posting.remote is False
    assert posting.posted_at is not None
    assert posting.posted_at.startswith("2026-")
    assert posting.tags == ("Software Development", "permanent")


def test_parse_remoteok_skips_the_legal_notice():
    (posting,) = parse_remoteok(REMOTEOK_PAYLOAD)
    assert posting.company == "Acme"
    assert posting.salary == "60000-90000"
    assert posting.url == "https://remoteok.com/remote-jobs/backend-engineer-acme-1137514"


def test_parse_hn_extracts_company_role_and_location():
    (posting,) = parse_hn(HN_PAYLOAD)
    assert posting.company == "PrairieLearn"
    assert posting.title == "Full-Stack Software Engineer"
    assert posting.location == "Remote US"
    assert posting.remote is True
    assert posting.url == "https://news.ycombinator.com/item?id=1"
    assert posting.external_id == "1"


def test_parse_hn_requires_a_header():
    """A comment with no company/role separator is chatter, not a posting."""
    assert len(parse_hn(HN_PAYLOAD)) == 1


def test_parse_rejects_unknown_source():
    with pytest.raises(ValueError, match="unknown source"):
        parse("monster", {})


def test_every_source_has_a_parser():
    assert set(PARSERS) == set(SOURCES)


def test_strip_html_handles_entities_and_whitespace():
    assert strip_html("A &amp; B<p>line</p>") == "A & B line"
    assert strip_html(None) == ""


def test_source_error_is_a_runtime_error():
    assert issubclass(SourceError, RuntimeError)


def test_parse_hn_drops_a_header_that_is_only_a_link():
    payload = {"children": [{"id": 9, "text": "https://futo.tech/ - FUTO"}]}
    assert parse_hn(payload) == []


def test_parse_hn_strips_links_out_of_company_and_role():
    payload = {"children": [{"id": 5, "text": "Acme https://acme.com - Backend Engineer"}]}
    (posting,) = parse_hn(payload)
    assert posting.company == "Acme"
    assert posting.title == "Backend Engineer"


ADZUNA_RESULT: dict[str, Any] = {
    "id": "5478654321",
    "title": "Junior Software Engineer",
    "company": {"display_name": "Acme Ltd"},
    "location": {"display_name": "London, UK", "area": ["UK", "London"]},
    "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/5478654321",
    "salary_min": 29000,
    "salary_max": 33000,
    "salary_is_predicted": 0,
    "category": {"label": "IT Jobs", "tag": "it-jobs"},
    "contract_time": "full_time",
    "created": "2026-10-14T09:00:00Z",
    "description": "<p>Graduate scheme in <b>Python</b></p>",
}


def test_parse_adzuna_reads_the_stated_salary():
    (posting,) = parse_adzuna({"results": [ADZUNA_RESULT]})
    assert posting.source == "adzuna"
    assert posting.title == "Junior Software Engineer"
    assert posting.company == "Acme Ltd"
    assert posting.location == "London, UK"
    assert posting.salary == "£29,000-£33,000"
    assert (posting.salary_min, posting.salary_max) == (29000, 33000)
    assert posting.salary_currency == "GBP"
    assert "it-jobs" in posting.tags
    assert posting.description == "Graduate scheme in Python"


def test_parse_adzuna_drops_predicted_salaries():
    """A predicted figure is a guess, not a stated salary."""
    (posting,) = parse_adzuna({"results": [dict(ADZUNA_RESULT, salary_is_predicted=1)]})
    assert posting.salary is None
    assert posting.salary_min is None
    assert posting.salary_max is None
    assert posting.salary_currency is None


def test_parse_adzuna_falls_back_to_the_area_list():
    payload = {"results": [dict(ADZUNA_RESULT, location={"area": ["UK", "London"]})]}
    (posting,) = parse_adzuna(payload)
    assert posting.location == "UK, London"


def test_parse_adzuna_needs_a_company():
    payload = {"results": [{"id": "1", "title": "Ghost Job"}]}
    assert parse_adzuna(payload) == []


def _adzuna_creds(*_args, **_kwargs):
    from jobhunt.credentials import AdzunaCredentials

    return AdzunaCredentials(app_id="id", app_key="key")


def _record_urls(monkeypatch, payloads=None):
    """Capture the URLs Adzuna would be called with, without any network."""
    asked: list[str] = []

    def fake_get_json(url):
        asked.append(url)
        return (payloads or {}).get(
            "remote" if "what_and=remote" in url else "place", {"results": []}
        )

    monkeypatch.setattr("jobhunt.sources._get_json", fake_get_json)
    monkeypatch.setattr("jobhunt.sources.load_adzuna", _adzuna_creds)
    return asked


def test_adzuna_runs_a_place_pass_and_a_remote_pass(monkeypatch):
    """A place filter must not hide remote work, so both are asked for."""
    asked = _record_urls(monkeypatch)

    fetch_adzuna(50, ["junior engineer"], where="london")

    assert len(asked) == 2
    assert "where=london" in asked[0]
    assert "what_and=remote" not in asked[0]
    assert "what_and=remote" in asked[1]
    assert "where=" not in asked[1]


def test_adzuna_without_a_place_makes_one_pass_per_query(monkeypatch):
    asked = _record_urls(monkeypatch)

    fetch_adzuna(50, ["a", "b"])

    assert len(asked) == 2
    assert all("where=" not in url for url in asked)


def test_adzuna_marks_the_remote_pass_as_remote(monkeypatch):
    """A Derry advert found by the remote pass is remote: that is the evidence."""
    _record_urls(
        monkeypatch,
        {
            "remote": {
                "results": [
                    {
                        "id": "1",
                        "title": "Junior Developer",
                        "company": {"display_name": "Acme"},
                        "location": {"display_name": "Derry, Northern Ireland"},
                    }
                ]
            }
        },
    )

    (posting,) = fetch_adzuna(50, ["junior developer"], where="london")
    assert posting.remote is True
    assert posting.location == "Derry, Northern Ireland"


class _Response:
    """The little of an HTTP response that `_get_json` touches."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_a_transient_server_error_is_retried(monkeypatch):
    """A board having a bad minute must not cost the whole day's search."""
    attempts: list[int] = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", None, None)
        return _Response(b'{"results": []}')

    monkeypatch.setattr("jobhunt.sources.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("jobhunt.sources.RETRY_DELAY_SECONDS", 0)

    assert _get_json("https://example.test/jobs") == {"results": []}
    assert len(attempts) == 3


def test_a_client_error_is_not_retried(monkeypatch):
    """A bad query or a revoked key will fail the same way every time."""
    attempts: list[int] = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", None, None)

    monkeypatch.setattr("jobhunt.sources.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("jobhunt.sources.RETRY_DELAY_SECONDS", 0)

    with pytest.raises(SourceError):
        _get_json("https://example.test/jobs")
    assert len(attempts) == 1


def test_a_board_that_stays_down_reports_the_failure(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", None, None)

    monkeypatch.setattr("jobhunt.sources.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("jobhunt.sources.RETRY_DELAY_SECONDS", 0)

    with pytest.raises(SourceError, match="503"):
        _get_json("https://example.test/jobs")
