"""Tests for the storage layer."""

from __future__ import annotations

import pytest

from jobhunt.models import Application, Posting
from jobhunt.storage import Store


@pytest.fixture()
def store(tmp_path):
    with Store(tmp_path / "test.db") as opened:
        yield opened


def test_add_assigns_id_and_timestamps(store):
    application = store.add(Application(company="Acme", role="Backend Engineer"))
    assert application.id == 1
    assert application.status == "saved"
    assert application.created_at
    assert application.updated_at


def test_get_roundtrip(store):
    created = store.add(Application(company="Acme", role="Dev", url="https://example.com/job"))
    assert store.get(created.id) == created


def test_get_missing_returns_none(store):
    assert store.get(999) is None


def test_list_filters_by_status(store):
    store.add(Application(company="A", role="Dev", status="applied"))
    store.add(Application(company="B", role="Dev", status="rejected"))
    assert [a.company for a in store.list("applied")] == ["A"]
    assert len(store.list()) == 2


def test_update_status_records_notes(store):
    application = store.add(Application(company="A", role="Dev"))
    updated = store.update_status(application.id, "interview", notes="call booked")
    assert updated.status == "interview"
    assert updated.notes == "call booked"


def test_update_missing_raises(store):
    with pytest.raises(KeyError):
        store.update_status(4242, "offer")


def test_delete(store):
    application = store.add(Application(company="A", role="Dev"))
    assert store.delete(application.id) is True
    assert store.delete(application.id) is False


def test_stats_counts_every_status(store):
    store.add(Application(company="A", role="Dev", status="applied"))
    store.add(Application(company="B", role="Dev", status="applied"))
    store.add(Application(company="C", role="Dev", status="offer"))
    counts = store.stats()
    assert counts["applied"] == 2
    assert counts["offer"] == 1
    assert counts["total"] == 3


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError):
        Application(company="A", role="Dev", status="ghosted")


def test_blank_company_is_rejected():
    with pytest.raises(ValueError):
        Application(company="   ", role="Dev")


def test_upsert_posting_inserts_once(store):
    posting = Posting(source="remotive", title="Dev", company="Acme", external_id="1")
    stored, is_new = store.upsert_posting(posting)
    assert is_new is True
    assert stored.id == 1

    again, is_new_again = store.upsert_posting(posting)
    assert is_new_again is False
    assert again.id == stored.id
    assert store.count_postings() == 1


def test_upsert_posting_dedupes_the_same_role_across_sources(store):
    first = Posting(source="remotive", title="Backend Engineer", company="Acme", external_id="1")
    second = Posting(source="remoteok", title="backend engineer", company="Acme ", external_id="9")
    assert store.upsert_posting(first)[1] is True
    assert store.upsert_posting(second)[1] is False
    assert store.count_postings() == 1


def test_posting_round_trip_preserves_every_field(store):
    posting = Posting(
        source="arbeitnow",
        title="Dev",
        company="Beta",
        external_id="x",
        url="https://example.com/1",
        location="Berlin",
        remote=True,
        salary="1-2",
        tags=("a", "b"),
        posted_at="2026-01-01T00:00:00+00:00",
        description="desc",
    )
    stored, _ = store.upsert_posting(posting)
    reloaded = store.get_posting(stored.id)
    assert reloaded == stored
    assert reloaded.key == posting.key


def test_list_postings_is_newest_first(store):
    first = store.upsert_posting(Posting(source="s", title="A", company="Co", external_id="1"))[0]
    second = store.upsert_posting(Posting(source="s", title="B", company="Co", external_id="2"))[0]
    assert [item.id for item in store.list_postings()] == [second.id, first.id]


def test_list_postings_filters_by_source_and_limit(store):
    store.upsert_posting(Posting(source="a", title="One", company="Co", external_id="1"))
    store.upsert_posting(Posting(source="b", title="Two", company="Co", external_id="2"))
    assert len(store.list_postings(source="a")) == 1
    assert len(store.list_postings(limit=1)) == 1


def test_get_posting_missing_returns_none(store):
    assert store.get_posting(500) is None
