"""Tests for the job-board parsers and the HTML helpers."""

from __future__ import annotations

from typing import Any

import pytest

from jobhunt.sources import (
    PARSERS,
    SOURCES,
    SourceError,
    parse,
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
