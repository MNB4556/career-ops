"""Filtering and ranking of discovered postings.

Terms match whole words rather than bare substrings, so ``intern`` does not
match ``internal``, and ``uk`` does not match ``Ukraine``. Common inflections
are still accepted, so ``engineer`` matches ``engineers`` and ``engineering``,
and ``intern`` matches ``interns`` and ``internship``.

``keywords`` and ``require`` are separate OR-groups and *both* must be
satisfied, which is what lets a search ask for "software roles **and** a junior
level" while rejecting a senior role that only matches the first group.

An advert that names a future year - "2027 Summer Internship" - is not a job
you can start now, so it is ranked below an otherwise equal one that is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from jobhunt.models import Posting, normalise

# Trailing forms that should still count as the same term.
_INFLECTIONS = ("s", "es", "ed", "ing", "ship", "ships")

_YEAR = re.compile(r"\b(20\d{2})\b")

# What a later start costs. Roughly one strong term hit, so a role starting next
# year never outranks a similar one that starts now, while still beating nothing.
_DEFERRED_PENALTY = 4

_NEVER = re.compile(r"(?!)")


@lru_cache(maxsize=1024)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile *term* into a whole-word pattern that tolerates inflections."""
    core = normalise(term)
    if not core:
        return _NEVER
    lead = r"\b" if re.match(r"\w", core) else ""
    tail = r"\b" if re.search(r"\w$", core) else ""
    suffixes = "|".join(_INFLECTIONS)
    return re.compile(rf"{lead}{re.escape(core)}(?:{suffixes})?{tail}")


def _contains(terms: tuple[str, ...], text: str) -> bool:
    """Whether any of *terms* appears in *text* on a word boundary."""
    return any(_term_pattern(term).search(text) for term in terms)


def deferred_year(posting: Posting, *, now_year: int | None = None) -> int | None:
    """Return the year *posting* starts, if that is later than *now_year*.

    A job advert only writes a future year when it is saying when the work
    begins: nothing about a company's past can be dated after today, so the
    earliest year past this one is a start date. That is worth knowing most in
    autumn, when the boards fill with "Summer 2027" adverts a year ahead.

    The description is searched as well as the title because adverts such as
    "Summer Intern Software Engineer" often carry the date only in the body.
    """
    reference = now_year if now_year is not None else datetime.now(UTC).year
    text = f"{posting.title} {posting.description or ''}"
    later = sorted(int(year) for year in _YEAR.findall(text) if int(year) > reference)
    return later[0] if later else None


@dataclass(frozen=True)
class Criteria:
    """What you are looking for. An empty field means "no constraint"."""

    keywords: tuple[str, ...] = ()
    require: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    remote_only: bool = False
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None

    def __post_init__(self) -> None:
        for field in ("keywords", "require", "exclude", "locations"):
            object.__setattr__(
                self, field, tuple(word for word in getattr(self, field) if word and word.strip())
            )
        if self.salary_currency:
            object.__setattr__(self, "salary_currency", self.salary_currency.strip().upper())

    def _scoring_terms(self) -> tuple[str, ...]:
        """Every positive term, de-duplicated but order-preserving."""
        return tuple(dict.fromkeys((*self.keywords, *self.require)))

    def _searchable(self, posting: Posting) -> str:
        """Everything about *posting* that plain keyword matching may look at."""
        parts = (
            posting.title,
            posting.company,
            " ".join(posting.tags),
            posting.description or "",
        )
        return normalise(" ".join(parts))

    def matches(self, posting: Posting) -> bool:
        """Whether *posting* survives every configured constraint."""
        searchable = self._searchable(posting)
        if _contains(self.exclude, searchable):
            return False
        if self.remote_only and not posting.remote:
            return False
        if not self._salary_fits(posting):
            return False
        if self.locations and not posting.remote:
            # A remote advert is location-independent, so it survives whatever
            # the locations list says: asking for "London or remote" must not
            # drop a remote role that happens to name Leeds. A named on-site
            # role still has to match, and one with no place at all is not
            # worth guessing at.
            location = normalise(posting.location or "")
            if not location or not _contains(self.locations, location):
                return False
        if self.keywords and not _contains(self.keywords, searchable):
            return False
        if self.require:
            return _contains(self.require, searchable)
        return True

    def _salary_fits(self, posting: Posting) -> bool:
        """Whether a *stated* salary overlaps the wanted band.

        Adverts that are silent about pay, or that pay in a currency that
        cannot be compared against, are kept: dropping a job because its advert
        omits a salary would quietly discard most junior roles. Only a stated
        figure in the same currency can rule an advert out.
        """
        if self.salary_min is None and self.salary_max is None:
            return True
        if posting.salary_min is None and posting.salary_max is None:
            return True
        if posting.salary_currency != self.salary_currency:
            return True
        if (
            self.salary_min is not None
            and posting.salary_max is not None
            and posting.salary_max < self.salary_min
        ):
            return False
        return not (
            self.salary_max is not None
            and posting.salary_min is not None
            and posting.salary_min > self.salary_max
        )

    def score(self, posting: Posting, *, now_year: int | None = None) -> int:
        """Rank an already-matching *posting*; a title hit is worth most.

        A role that cannot start until a later year loses :data:`_DEFERRED_PENALTY`,
        which is what pushes next year's internship intake below the jobs on
        offer today.
        """
        title = normalise(posting.title)
        searchable = self._searchable(posting)
        score = 0
        for term in self._scoring_terms():
            pattern = _term_pattern(term)
            if pattern.search(title):
                score += 3
            elif pattern.search(searchable):
                score += 1
        location = normalise(posting.location or "")
        score += sum(1 for term in self.locations if _term_pattern(term).search(location))
        if posting.remote:
            score += 1
        if deferred_year(posting, now_year=now_year) is not None:
            # Never below zero: a negative score would fall under the default
            # minimum and delete the advert rather than rank it last.
            score = max(0, score - _DEFERRED_PENALTY)
        return score

    def rank(
        self, postings: list[Posting], *, now_year: int | None = None
    ) -> list[tuple[Posting, int]]:
        """Filter *postings* and return ``(posting, score)`` pairs, best first.

        Ties keep their original order so results stay stable between runs.
        """
        scored = [
            (posting, self.score(posting, now_year=now_year))
            for posting in postings
            if self.matches(posting)
        ]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)
