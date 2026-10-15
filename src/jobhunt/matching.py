"""Filtering and ranking of discovered postings.

The rules are deliberately simple and explainable: keywords must all be
satisfiable by a single posting (any one match is enough), exclusions veto a
posting outright, and scoring only ever promotes a posting the filters already
accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobhunt.models import Posting, normalise


@dataclass(frozen=True)
class Criteria:
    """What you are looking for. An empty field means "no constraint"."""

    keywords: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    remote_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "keywords", tuple(word for word in self.keywords if word and word.strip())
        )
        object.__setattr__(
            self, "exclude", tuple(word for word in self.exclude if word and word.strip())
        )
        object.__setattr__(
            self, "locations", tuple(word for word in self.locations if word and word.strip())
        )

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
        if any(normalise(term) in searchable for term in self.exclude):
            return False
        if self.remote_only and not posting.remote:
            return False
        if self.locations:
            location = normalise(posting.location or "")
            if location:
                if not any(normalise(term) in location for term in self.locations):
                    return False
            elif not posting.remote:
                # No stated location on an on-site role: not worth guessing at.
                return False
        if self.keywords:
            return any(normalise(term) in searchable for term in self.keywords)
        return True

    def score(self, posting: Posting) -> int:
        """Rank an already-matching *posting*; a title hit is worth most."""
        title = normalise(posting.title)
        searchable = self._searchable(posting)
        score = 0
        for keyword in self.keywords:
            term = normalise(keyword)
            if term in title:
                score += 3
            elif term in searchable:
                score += 1
        location = normalise(posting.location or "")
        score += sum(1 for term in self.locations if normalise(term) in location)
        if posting.remote:
            score += 1
        return score

    def rank(self, postings: list[Posting]) -> list[tuple[Posting, int]]:
        """Filter *postings* and return ``(posting, score)`` pairs, best first.

        Ties keep their original order so results stay stable between runs.
        """
        scored = [(posting, self.score(posting)) for posting in postings if self.matches(posting)]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)
