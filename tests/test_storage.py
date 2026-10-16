"""Tests for the storage layer."""

from __future__ import annotations

import sqlite3

import pytest

from jobhunt.models import Application, Posting, today
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


def test_posting_salary_round_trips(store):
    stored, _ = store.upsert_posting(
        Posting(
            source="adzuna",
            title="Dev",
            company="Acme",
            external_id="1",
            salary="£29,000-£33,000",
            salary_min=29000,
            salary_max=33000,
            salary_currency="GBP",
        )
    )
    reloaded = store.get_posting(stored.id)
    assert reloaded.salary == "£29,000-£33,000"
    assert (reloaded.salary_min, reloaded.salary_max) == (29000, 33000)
    assert reloaded.salary_currency == "GBP"


def test_legacy_databases_gain_the_salary_columns(tmp_path):
    """A database from before salaries were stored is upgraded, not discarded."""
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE postings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            signature TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT,
            location TEXT,
            remote INTEGER NOT NULL DEFAULT 0,
            salary TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            posted_at TEXT,
            description TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        """
    )
    legacy.commit()
    legacy.close()

    with Store(path) as store:
        stored, is_new = store.upsert_posting(
            Posting(
                source="adzuna",
                title="Junior Dev",
                company="Acme",
                external_id="1",
                salary_min=29000,
                salary_max=33000,
                salary_currency="GBP",
            )
        )

    assert is_new is True
    assert stored.salary_min == 29000
    assert stored.salary_currency == "GBP"


def test_an_application_remembers_the_posting_it_came_from(store):
    posting = store.upsert_posting(
        Posting(source="adzuna", title="Junior Dev", company="Acme", external_id="1")
    )[0]
    application = store.add(posting.to_application())
    assert application.posting_id == posting.id
    assert store.find_by_posting(posting.id) == application


def test_find_by_posting_is_none_when_nothing_tracks_it(store):
    assert store.find_by_posting(7) is None


def test_status_changes_are_recorded_as_history(store):
    """Only keeping the current status would lose when each move happened."""
    application = store.add(Application(company="A", role="Dev"))
    store.update_status(application.id, "applied")
    store.update_status(application.id, "interview", notes="call booked")

    assert [(event.status, event.note) for event in store.timeline(application.id)] == [
        ("saved", None),
        ("applied", None),
        ("interview", "call booked"),
    ]


def test_the_first_move_to_applied_stamps_the_date(store):
    """``applied_on`` is what a follow-up is measured from, so it is automatic."""
    application = store.add(Application(company="A", role="Dev"))
    assert application.applied_on is None

    applied = store.update_status(application.id, "applied")
    assert applied.applied_on == today()


def test_deleting_an_application_takes_its_history_with_it(store):
    application = store.add(Application(company="A", role="Dev"))
    store.update_status(application.id, "applied")

    assert store.delete(application.id) is True
    assert store.timeline(application.id) == []


def test_open_applications_keep_an_unanswered_offer_but_drop_closed(store):
    store.add(Application(company="Offer", role="Dev", status="offer"))
    store.add(Application(company="Rejected", role="Dev", status="rejected"))
    store.add(Application(company="Withdrawn", role="Dev", status="withdrawn"))

    assert [application.company for application in store.list_open()] == ["Offer"]


def test_legacy_application_tables_gain_the_posting_link(tmp_path):
    """A tracker from before postings were linked is upgraded, not discarded."""
    path = tmp_path / "legacy-apps.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE applications (
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
        """
    )
    legacy.commit()
    legacy.close()

    with Store(path) as store:
        application = store.add(Application(company="A", role="Dev", posting_id=7))

    assert application.posting_id == 7
