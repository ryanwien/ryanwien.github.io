"""Research notes, the assumptions behind them, and the evidence label on each assumption.

Owns the domain vocabulary. Invariants:

- An assumption labelled ``supported`` or ``mixed`` always cites a source. Evidence that
  cannot be pointed at is, by definition, unverified.
- Notes and assumptions are immutable values; the store swaps whole values on change.
- Text fields are stripped and length-limited, so the summary never has to defend
  against empty or runaway input.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

MAX_QUESTION_LENGTH: Final = 300
MAX_STATEMENT_LENGTH: Final = 500
MAX_TEXT_LENGTH: Final = 2000
MAX_SOURCE_LENGTH: Final = 500
MAX_ASSUMPTIONS_PER_NOTE: Final = 100


class Evidence(StrEnum):
    """How well an assumption is backed, as judged by the analyst."""

    SUPPORTED = "supported"  # a cited source backs it
    MIXED = "mixed"  # sources disagree, or back it only in part
    UNVERIFIED = "unverified"  # nobody has found a source yet


class ThesisTraceError(Exception):
    """Base for every domain error."""

    code: str = "thesistrace_error"


class NotFoundError(ThesisTraceError):
    """A note or assumption id does not exist."""

    code = "not_found"


class MissingSourceError(ThesisTraceError):
    """An assumption was labelled supported or mixed without citing a source."""

    code = "missing_source"


class InvalidTextError(ThesisTraceError):
    """A required text field is blank or a field is longer than its limit."""

    code = "invalid_text"


class LimitError(ThesisTraceError):
    """A note already holds the maximum number of assumptions."""

    code = "limit_reached"


def clean_text(value: str, *, name: str, limit: int, required: bool) -> str:
    """Strip ``value`` and enforce its length limit; blank is an error when ``required``."""
    text = value.strip()
    if required and not text:
        raise InvalidTextError(f"{name} cannot be blank")
    if len(text) > limit:
        raise InvalidTextError(f"{name} is longer than {limit} characters")
    return text


def clean_source(value: str | None) -> str | None:
    """Normalise a source citation; blank becomes ``None``."""
    if value is None:
        return None
    text = clean_text(value, name="source", limit=MAX_SOURCE_LENGTH, required=False)
    return text or None


@dataclass(frozen=True, slots=True)
class Assumption:
    """One claim the conclusion depends on, with its evidence label."""

    id: str
    statement: str
    evidence: Evidence = Evidence.UNVERIFIED
    source: str | None = None
    rationale: str = ""
    critical: bool = False  # load-bearing: the conclusion falls if this is wrong

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "statement",
            clean_text(self.statement, name="statement", limit=MAX_STATEMENT_LENGTH, required=True),
        )
        object.__setattr__(
            self,
            "rationale",
            clean_text(self.rationale, name="rationale", limit=MAX_TEXT_LENGTH, required=False),
        )
        object.__setattr__(self, "evidence", Evidence(self.evidence))
        object.__setattr__(self, "source", clean_source(self.source))
        if self.evidence is not Evidence.UNVERIFIED and self.source is None:
            raise MissingSourceError(
                f"an assumption marked {self.evidence.value} needs a source; "
                "cite one or mark it unverified"
            )


@dataclass(frozen=True, slots=True)
class ResearchNote:
    """A question, the tentative conclusion, and the assumptions it rests on."""

    id: str
    question: str
    context: str = ""
    conclusion: str = ""
    assumptions: tuple[Assumption, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "question",
            clean_text(self.question, name="question", limit=MAX_QUESTION_LENGTH, required=True),
        )
        object.__setattr__(
            self,
            "context",
            clean_text(self.context, name="context", limit=MAX_TEXT_LENGTH, required=False),
        )
        object.__setattr__(
            self,
            "conclusion",
            clean_text(self.conclusion, name="conclusion", limit=MAX_TEXT_LENGTH, required=False),
        )
        if len(self.assumptions) > MAX_ASSUMPTIONS_PER_NOTE:
            raise LimitError(f"a note holds at most {MAX_ASSUMPTIONS_PER_NOTE} assumptions")

    def assumption(self, assumption_id: str) -> Assumption:
        """Return the assumption with ``assumption_id`` or raise :class:`NotFoundError`."""
        for item in self.assumptions:
            if item.id == assumption_id:
                return item
        raise NotFoundError(f"assumption {assumption_id} not found in note {self.id}")
