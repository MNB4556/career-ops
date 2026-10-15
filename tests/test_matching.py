"""Tests for posting filtering and ranking."""

from __future__ import annotations

from jobhunt.matching import Criteria
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
    assert Criteria(keywords=("python",)).matches(posting(description="Uses PYTHON daily"))


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
    assert not Criteria(require=("intern",)).matches(posting(description="internal tooling"))
    assert Criteria(require=("intern",)).matches(posting(description="internal tooling, interns"))


def test_uk_does_not_match_ukraine():
    assert not Criteria(locations=("uk",)).matches(posting(location="Kyiv, Ukraine"))
    assert Criteria(locations=("uk",)).matches(posting(location="London, UK"))


def test_inflections_still_match():
    assert Criteria(keywords=("engineer",)).matches(posting(title="Engineering Manager role"))
    assert Criteria(keywords=("engineer",)).matches(posting(title="Backend Engineers wanted"))
    assert Criteria(require=("intern",)).matches(posting(title="Summer Internship"))
    assert Criteria(keywords=("graduate",)).matches(posting(description="graduates welcome"))


def test_location_filter_drops_onsite_roles_with_unknown_location():
    assert not Criteria(locations=("london",)).matches(posting(location=None))


def test_location_filter_keeps_remote_roles_with_unknown_location():
    """A remote role with no stated location might still be fine, so keep it."""
    assert Criteria(locations=("london",)).matches(posting(location=None, remote=True))


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
    assert Criteria(require=("junior",)).matches(posting(description="a junior role"))
    assert not Criteria(require=("junior",)).matches(posting())


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
