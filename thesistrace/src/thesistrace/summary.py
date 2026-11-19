"""The evidence summary: what is proven, what is uncertain, what still needs a source.

Pure function of a :class:`~thesistrace.domain.ResearchNote`. Invariants:

- Every assumption lands in exactly one bucket (proven, uncertain, needs a source).
- Shares are whole percentages that sum to exactly 100 (largest-remainder rounding),
  or are all zero when there are no assumptions.
- The verdict is the most severe condition present, in this order: a critical
  assumption without a source, any assumption without a source, any mixed evidence.
  Only a note whose every assumption is sourced and supported reads as supported.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from thesistrace.domain import Assumption, Evidence, ResearchNote

PERCENT: Final = 100


class Verdict(StrEnum):
    """How far a reviewer can lean on the note's conclusion today."""

    EMPTY = "empty"
    BLOCKED = "blocked"
    NEEDS_SOURCES = "needs_sources"
    CONTESTED = "contested"
    SUPPORTED = "supported"


HEADLINES: Final[dict[Verdict, str]] = {
    Verdict.EMPTY: "No assumptions yet. List what the conclusion depends on.",
    Verdict.BLOCKED: "Not ready to trust: a load-bearing assumption has no source.",
    Verdict.NEEDS_SOURCES: "Usable with care: some assumptions still need a source.",
    Verdict.CONTESTED: "Every assumption is sourced, but some of the evidence is mixed.",
    Verdict.SUPPORTED: "Every assumption is sourced and supported.",
}


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """The reviewer's view of a note, recomputed on every change."""

    total: int
    counts: dict[Evidence, int]
    shares: dict[Evidence, int]
    verdict: Verdict
    headline: str
    proven: tuple[str, ...]
    uncertain: tuple[str, ...]
    needs_source: tuple[str, ...]
    critical_open: int


def whole_percentages(counts: dict[Evidence, int]) -> dict[Evidence, int]:
    """Largest-remainder rounding: whole percentages that sum to exactly 100.

    Ties in the remainder go to the earlier label in :class:`Evidence` order, so the
    result is deterministic.
    """
    total = sum(counts.values())
    if total == 0:
        return dict.fromkeys(Evidence, 0)
    floors = {label: counts[label] * PERCENT // total for label in Evidence}
    remainders = {label: counts[label] * PERCENT % total for label in Evidence}
    left = PERCENT - sum(floors.values())
    order = list(Evidence)
    by_remainder = sorted(order, key=lambda label: (-remainders[label], order.index(label)))
    for label in by_remainder[:left]:
        floors[label] += 1
    return floors


def _critical_first(items: list[Assumption]) -> tuple[str, ...]:
    """Ids with load-bearing assumptions first, otherwise in the note's order."""
    return tuple(a.id for a in sorted(items, key=lambda a: not a.critical))


def summarize(note: ResearchNote) -> EvidenceSummary:
    """Build the evidence summary for ``note``."""
    by_label: dict[Evidence, list[Assumption]] = {label: [] for label in Evidence}
    for item in note.assumptions:
        by_label[item.evidence].append(item)
    counts = {label: len(items) for label, items in by_label.items()}
    unverified = by_label[Evidence.UNVERIFIED]
    critical_open = sum(1 for a in unverified if a.critical)

    if not note.assumptions:
        verdict = Verdict.EMPTY
    elif critical_open:
        verdict = Verdict.BLOCKED
    elif unverified:
        verdict = Verdict.NEEDS_SOURCES
    elif by_label[Evidence.MIXED]:
        verdict = Verdict.CONTESTED
    else:
        verdict = Verdict.SUPPORTED

    return EvidenceSummary(
        total=len(note.assumptions),
        counts=counts,
        shares=whole_percentages(counts),
        verdict=verdict,
        headline=HEADLINES[verdict],
        proven=_critical_first(by_label[Evidence.SUPPORTED]),
        uncertain=_critical_first(by_label[Evidence.MIXED]),
        needs_source=_critical_first(unverified),
        critical_open=critical_open,
    )
