"""The sample note: a fictional company, used to seed the demo and to drive ``thesistrace.run``.

Every name and figure here is invented. The note exists to show each evidence label and
each part of the summary, not to say anything about a real business.
"""

from typing import Final

from thesistrace.domain import Evidence, ResearchNote
from thesistrace.store import NoteStore

QUESTION: Final = "Can Larkmoor Freight Lines (fictional) keep paying its dividend through FY2027?"
CONTEXT: Final = (
    "Mid-sized regional carrier. Dividend is 40% of free cash flow today. Board review "
    "of capital allocation is due next quarter."
)
CONCLUSION: Final = (
    "Tentatively yes, provided freight volumes hold and the refinancing closes on the "
    "terms in the term sheet."
)

# (statement, evidence, source, rationale, critical)
ASSUMPTIONS: Final[tuple[tuple[str, Evidence, str | None, str, bool], ...]] = (
    (
        "Free cash flow stays above $120M a year through FY2027.",
        Evidence.SUPPORTED,
        "FY2025 annual report, cash flow statement, p. 48",
        "Three years above $140M; guidance repeats the range.",
        True,
    ),
    (
        "The 2026 debt refinancing closes below 6.5%.",
        Evidence.MIXED,
        "Term sheet summary in the Q3 call transcript",
        "Management quotes 6.1%; two analysts on the call expect wider spreads.",
        True,
    ),
    (
        "Freight volumes in its regions do not fall more than 5% in 2026.",
        Evidence.UNVERIFIED,
        None,
        "No regional volume series found yet.",
        True,
    ),
    (
        "No large capital project is planned before FY2027.",
        Evidence.SUPPORTED,
        "Investor day slides, capex plan, slide 12",
        "",
        False,
    ),
    (
        "Fuel surcharges continue to pass through to customers.",
        Evidence.UNVERIFIED,
        None,
        "Contract terms not public; ask investor relations.",
        False,
    ),
)


def seed(store: NoteStore) -> ResearchNote:
    """Add the sample note to ``store`` and return it."""
    note = store.create_note(QUESTION, CONTEXT, CONCLUSION)
    for statement, evidence, source, rationale, critical in ASSUMPTIONS:
        note, _ = store.add_assumption(
            note.id,
            statement,
            evidence=evidence,
            source=source,
            rationale=rationale,
            critical=critical,
        )
    return note
