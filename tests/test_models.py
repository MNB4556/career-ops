"""Tests for the Posting model."""

from __future__ import annotations

import pytest

from jobhunt.models import Posting, normalise


def test_posting_key_prefers_the_external_id():
    posting = Posting(source="remotive", title="Dev", company="Acme", external_id="42")
    assert posting.key == "remotive:42"


def test_posting_key_falls_back_to_the_url():
    posting = Posting(source="hn", title="Dev", company="Acme", url="https://example.com/1")
    assert posting.key == "hn:https://example.com/1"


def test_posting_key_falls_back_to_company_and_title():
    posting = Posting(source="hn", title="Dev", company="Acme")
    assert posting.key == "hn:Acme|Dev"


def test_source_is_lowercased():
    assert Posting(source="RemoteOK", title="Dev", company="Acme").source == "remoteok"


def test_signature_ignores_case_and_spacing():
    first = Posting(source="a", title="Backend  Engineer", company="ACME")
    second = Posting(source="b", title="backend engineer", company="Acme ")
    assert first.signature == second.signature


def test_blank_tags_are_dropped():
    posting = Posting(source="a", title="Dev", company="Acme", tags=("python", "  ", ""))
    assert posting.tags == ("python",)


@pytest.mark.parametrize(
    ("field", "value"),
    [("title", "   "), ("company", ""), ("source", " ")],
)
def test_required_fields_are_enforced(field, value):
    fields = {"source": "a", "title": "Dev", "company": "Acme"}
    fields[field] = value
    with pytest.raises(ValueError):
        Posting(**fields)


def test_to_application_carries_the_link_and_source():
    posting = Posting(
        source="remoteok",
        title="Backend Engineer",
        company="Acme",
        url="https://example.com/job",
    )
    application = posting.to_application()
    assert application.company == "Acme"
    assert application.role == "Backend Engineer"
    assert application.url == "https://example.com/job"
    assert application.source == "remoteok"
    assert application.status == "saved"


def test_normalise_collapses_whitespace_and_case():
    assert normalise("  Backend   Engineer ") == "backend engineer"
