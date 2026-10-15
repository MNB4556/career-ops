"""Filtering and ranking of discovered postings.

Terms match whole words rather than bare substrings, so ``intern`` does not
match ``internal``, and ``uk`` does not match ``Ukraine``. Common inflections
are still accepted, so ``engineer`` matches ``engineers`` and ``engineering``,
and ``intern`` matches ``interns`` and ``internship``.

``keywords`` and ``require`` are separate OR-groups and *both* must be
satisfied, which is what lets a search ask for "software roles **and** a junior
level" while rejecting a senior role that only matches the first group.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from jobhunt.models import Posting, normalise

# Trailing forms that should still count as the same term.
_INFLECTIONS = ("s", "es", "ed", "ing", "ship", "ships")

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


@dataclass(frozen=True)
class Criteria:
    """What you are looking for. An empty field means "no constraint"."""

    keywords: tuple[str, ...] = ()
    require: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    remote_only: bool = False

    def __post_init__(self) -> None:
        for field in ("keywords", "require", "exclude", "locations"):
            object.__setattr__(
                self, field, tuple(word for word in getattr(self, field) if word and word.strip())
            )

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
        if self.locations:
            location = normalise(posting.location or "")
            if location:
                if not _contains(self.locations, location):
                    return False
            elif not posting.remote:
                # No stated location on an on-site role: not worth guessing at.
                return False
        if self.keywords and not _contains(self.keywords, searchable):
            return False
        if self.require:
            return _contains(self.require, searchable)
        return True

    def score(self, posting: Posting) -> int:
        """Rank an already-matching *posting*; a title hit is worth most."""
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
        return score

    def rank(self, postings: list[Posting]) -> list[tuple[Posting, int]]:
        """Filter *postings* and return ``(posting, score)`` pairs, best first.

        Ties keep their original order so results stay stable between runs.
        """
        scored = [(posting, self.score(posting)) for posting in postings if self.matches(posting)]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)
