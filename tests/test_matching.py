"""Tests for posting filtering and ranking."""

from __future__ import annotations

from datetime import UTC, datetime

from jobhunt.matching import Criteria, deferred_year
from jobhunt.models import Posting


def posting(**overrides: object) -> Posting:
    """Build a Posting with sensible defaults for the field under test."""
    fields: dict[str, object] = {
        "source": "test",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "London",
        "remote": False,
        "tags": ("python",),
        "description": "Build services",
    }
    fields.update(overrides)
    return Posting(**fields)  # type: ignore[arg-type]


def test_no_criteria_matches_everything():
    criteria = Criteria()
    assert criteria.matches(posting())
    assert criteria.score(posting()) == 0


def test_empty_keyword_strings_are_ignored():
    criteria = Criteria(keywords=("", "   "))
    assert criteria.matches(posting())


def test_keyword_matches_are_case_insensitive():
    assert Criteria(keywords=("python",)).matches(posting(title="PYTHON Developer"))


def test_a_keyword_only_in_the_description_is_not_enough():
    """An advert has to name the job; prose is not evidence it is yours."""
    advert = posting(
        title="Travel Support Specialist",
        company="Aisles & Abroad",
        tags=("travel", "customer support", "non tech"),
        description="This is an entry-level opportunity. We use python for reports.",
    )
    assert not Criteria(keywords=("python",)).matches(advert)
    assert not Criteria(keywords=("software", "engineer", "developer"), require=("entry",)).matches(
        advert
    )


def test_keywords_are_any_of_not_all():
    criteria = Criteria(keywords=("rust", "python"))
    assert criteria.matches(posting(tags=("python",)))


def test_keyword_absent_everywhere_fails():
    assert not Criteria(keywords=("cobol",)).matches(posting())


def test_exclude_vetoes_a_match():
    criteria = Criteria(keywords=("engineer",), exclude=("senior",))
    assert not criteria.matches(posting(title="Senior Backend Engineer"))


def test_exclude_checks_tags_too():
    assert not Criteria(exclude=("python",)).matches(posting())


def test_remote_only_drops_on_site_roles():
    assert not Criteria(remote_only=True).matches(posting(remote=False))
    assert Criteria(remote_only=True).matches(posting(remote=True))


def test_location_filter_matches_whole_words():
    assert Criteria(locations=("london",)).matches(posting(location="London, UK"))
    assert not Criteria(locations=("london",)).matches(posting(location="Berlin"))


def test_short_terms_do_not_match_unrelated_words():
    """The whole-word rule is what stops 'intern' matching 'internal'."""
    criteria = Criteria(keywords=("engineer",), require=("intern",))
    assert not criteria.matches(posting(title="Platform Engineer", description="internal tooling"))
    assert criteria.matches(posting(title="Platform Engineer", description="summer interns"))


def test_uk_does_not_match_ukraine():
    assert not Criteria(locations=("uk",)).matches(posting(location="Kyiv, Ukraine"))
    assert Criteria(locations=("uk",)).matches(posting(location="London, UK"))


def test_inflections_still_match():
    assert Criteria(keywords=("engineer",)).matches(posting(title="Engineering Manager role"))
    assert Criteria(keywords=("engineer",)).matches(posting(title="Backend Engineers wanted"))
    assert Criteria(require=("intern",)).matches(posting(title="Summer Internship"))
    assert Criteria(keywords=("graduate",)).matches(posting(title="Graduates welcome"))


def test_location_filter_drops_onsite_roles_with_unknown_location():
    assert not Criteria(locations=("london",)).matches(posting(location=None))


def test_location_filter_keeps_remote_roles_with_unknown_location():
    """A remote role with no stated location might still be fine, so keep it."""
    assert Criteria(locations=("london",)).matches(posting(location=None, remote=True))


def test_a_remote_role_survives_a_named_place_it_does_not_match():
    """Asking for "London or remote" must not drop a remote role listing Leeds."""
    criteria = Criteria(locations=("london", "remote"))
    assert criteria.matches(posting(location="Leeds, UK", remote=True))
    assert not criteria.matches(posting(location="Leeds, UK", remote=False))


def test_title_hits_score_higher_than_body_hits():
    criteria = Criteria(keywords=("python",))
    assert criteria.score(posting(title="Python Developer")) > criteria.score(
        posting(title="Backend Engineer", description="some python")
    )


def test_remote_and_location_add_to_the_score():
    criteria = Criteria(locations=("london",))
    assert criteria.score(posting(location="London", remote=True)) == 2


def test_rank_filters_and_orders_by_score():
    criteria = Criteria(keywords=("python",))
    weak = posting(title="Analyst", description="python")
    strong = posting(title="Python Engineer")
    ranked = criteria.rank([weak, strong])
    assert [item.title for item, _ in ranked] == ["Python Engineer", "Analyst"]


def test_rank_keeps_input_order_for_ties():
    criteria = Criteria()
    first, second = posting(company="A"), posting(company="B")
    ranked = criteria.rank([first, second])
    assert [item.company for item, _ in ranked] == ["A", "B"]


def test_require_is_a_second_gate_beside_keywords():
    """keywords and require are separate OR-groups, and both must be satisfied."""
    criteria = Criteria(keywords=("engineer", "developer"), require=("junior", "graduate"))
    assert criteria.matches(posting(title="Junior Software Engineer"))
    assert not criteria.matches(posting(title="Senior Software Engineer"))
    assert not criteria.matches(posting(title="Junior Sales Executive"))


def test_require_alone_is_enough():
    assert Criteria(require=("junior",)).matches(posting(title="Junior Developer"))
    assert not Criteria(require=("junior",)).matches(posting(title="Backend Engineer"))


def test_blank_require_entries_are_ignored():
    assert Criteria(require=("", "   ")).matches(posting())


def test_require_hits_contribute_to_the_score():
    criteria = Criteria(require=("junior",))
    assert criteria.score(posting(title="Junior Developer")) > criteria.score(
        posting(description="junior")
    )


def test_a_term_in_both_groups_is_not_counted_twice():
    criteria = Criteria(keywords=("python",), require=("python",))
    assert criteria.score(posting(title="Python Developer")) == 3


def test_salary_outside_the_band_is_dropped():
    criteria = Criteria(salary_min=29000, salary_max=35000, salary_currency="GBP")
    assert not criteria.matches(posting(salary_min=50000, salary_max=70000, salary_currency="GBP"))
    assert not criteria.matches(posting(salary_min=18000, salary_max=22000, salary_currency="GBP"))


def test_salary_overlapping_the_band_is_kept():
    criteria = Criteria(salary_min=29000, salary_max=35000, salary_currency="GBP")
    assert criteria.matches(posting(salary_min=28000, salary_max=40000, salary_currency="GBP"))
    assert criteria.matches(posting(salary_min=31000, salary_max=31000, salary_currency="GBP"))


def test_an_advert_with_no_salary_is_kept():
    """Dropping silent adverts would quietly discard most junior roles."""
    criteria = Criteria(salary_min=29000, salary_max=35000, salary_currency="GBP")
    assert criteria.matches(posting())


def test_a_salary_in_another_currency_is_kept():
    criteria = Criteria(salary_min=29000, salary_max=35000, salary_currency="GBP")
    assert criteria.matches(posting(salary_min=60000, salary_max=90000, salary_currency="USD"))


def test_a_salary_on_the_boundary_is_kept():
    criteria = Criteria(salary_min=29000, salary_currency="GBP")
    assert criteria.matches(posting(salary_max=29000, salary_currency="GBP"))
    assert not criteria.matches(posting(salary_max=28999, salary_currency="GBP"))


def test_no_salary_criteria_ignores_salaries_entirely():
    assert Criteria().matches(posting(salary_min=500000, salary_max=900000, salary_currency="GBP"))


def test_a_later_start_year_is_reported():
    next_year = datetime.now(UTC).year + 1
    assert deferred_year(posting(title=f"Summer Internship {next_year}")) == next_year


def test_the_earliest_later_year_wins():
    next_year = datetime.now(UTC).year + 1
    found = deferred_year(posting(title=f"Graduate Programme {next_year}-{next_year + 1}"))
    assert found == next_year


def test_this_year_and_the_past_are_not_start_dates():
    """Only a year still to come means the job is not open yet."""
    this_year = datetime.now(UTC).year
    assert deferred_year(posting(title=f"Graduate Programme {this_year}")) is None
    assert deferred_year(posting(title="Engineer", description="Founded 1998")) is None


def test_a_start_date_only_in_the_body_is_found():
    next_year = datetime.now(UTC).year + 1
    assert deferred_year(posting(description=f"Programme starts: June {next_year}")) == next_year


def test_a_role_starting_later_ranks_below_one_starting_now():
    criteria = Criteria(keywords=("python",))
    soon = posting(title="Python Developer")
    later = posting(title="Python Developer 2027", company="Beta")

    ranked = criteria.rank([later, soon], now_year=2026)

    assert [found.title for found, _ in ranked] == ["Python Developer", "Python Developer 2027"]


def test_a_role_starting_later_is_still_matched():
    """Demoted, not hidden: next year's intake is still worth seeing."""
    criteria = Criteria(keywords=("python",))
    assert criteria.matches(posting(title="Python Intern 2027"))


def test_hide_deferred_drops_a_role_that_cannot_start_yet():
    """Wanting work now is a different question from next year's intake."""
    next_year = datetime.now(UTC).year + 1
    criteria = Criteria(keywords=("engineer",), hide_deferred=True)
    assert not criteria.matches(posting(title=f"Engineering Intern {next_year}"))
    assert criteria.matches(posting(title="Engineering Intern"))


def test_deferred_roles_survive_unless_asked_to_hide_them():
    next_year = datetime.now(UTC).year + 1
    assert Criteria(keywords=("engineer",)).matches(
        posting(title=f"Engineering Intern {next_year}")
    )
