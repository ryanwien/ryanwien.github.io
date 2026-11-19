"""The evidence summary as a pure function, and the domain rules it relies on."""

from itertools import product

import pytest

from thesistrace.domain import (
    MAX_ASSUMPTIONS_PER_NOTE,
    Assumption,
    Evidence,
    InvalidTextError,
    LimitError,
    MissingSourceError,
    ResearchNote,
)
from thesistrace.store import NoteStore
from thesistrace.summary import Verdict, summarize, whole_percentages


def _note(*specs: tuple[Evidence, bool]) -> ResearchNote:
    items = tuple(
        Assumption(
            id=f"a{i}",
            statement=f"claim {i}",
            evidence=evidence,
            source=None if evidence is Evidence.UNVERIFIED else "a source",
            critical=critical,
        )
        for i, (evidence, critical) in enumerate(specs)
    )
    return ResearchNote(id="n", question="q?", assumptions=items)


S, M, U = Evidence.SUPPORTED, Evidence.MIXED, Evidence.UNVERIFIED


@pytest.mark.parametrize(
    ("specs", "verdict"),
    [
        ((), Verdict.EMPTY),
        (((S, True),), Verdict.SUPPORTED),
        (((S, False), (M, True)), Verdict.CONTESTED),
        (((S, True), (U, False)), Verdict.NEEDS_SOURCES),
        (((M, False), (U, False)), Verdict.NEEDS_SOURCES),
        (((S, True), (M, True), (U, True)), Verdict.BLOCKED),
        (((U, True),), Verdict.BLOCKED),
    ],
)
def test_verdict_is_the_most_severe_condition(specs, verdict):
    assert summarize(_note(*specs)).verdict is verdict


def test_every_assumption_lands_in_exactly_one_bucket():
    # Every combination of three assumptions' labels and load-bearing flags.
    options = list(product(Evidence, (False, True)))
    for combo in product(options, repeat=3):
        summary = summarize(_note(*combo))
        buckets = summary.proven + summary.uncertain + summary.needs_source
        assert sorted(buckets) == ["a0", "a1", "a2"]
        assert sum(summary.counts.values()) == summary.total == 3
        assert sum(summary.shares.values()) == 100


def test_load_bearing_assumptions_are_listed_first():
    summary = summarize(_note((U, False), (U, True), (U, False), (U, True)))
    assert summary.needs_source == ("a1", "a3", "a0", "a2")
    assert summary.critical_open == 2


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ((0, 0, 0), (0, 0, 0)),
        ((1, 1, 1), (34, 33, 33)),
        ((2, 1, 0), (67, 33, 0)),
        ((1, 0, 6), (14, 0, 86)),
        ((5, 0, 0), (100, 0, 0)),
    ],
)
def test_whole_percentages_sum_to_100(counts, expected):
    shares = whole_percentages(dict(zip(Evidence, counts, strict=True)))
    assert tuple(shares[label] for label in Evidence) == expected


def test_every_split_up_to_30_sums_to_100():
    for counts in product(range(11), repeat=3):
        if sum(counts):
            shares = whole_percentages(dict(zip(Evidence, counts, strict=True)))
            assert sum(shares.values()) == 100
            for label, n in zip(Evidence, counts, strict=True):
                if n == 0:
                    assert shares[label] == 0


@pytest.mark.parametrize("evidence", [S, M])
@pytest.mark.parametrize("source", [None, "", "   "])
def test_sourced_labels_need_a_real_source(evidence, source):
    with pytest.raises(MissingSourceError):
        Assumption(id="a", statement="claim", evidence=evidence, source=source)


def test_unverified_may_keep_a_source_it_is_still_checking():
    item = Assumption(id="a", statement="claim", source="  lead: IR call  ")
    assert item.source == "lead: IR call"


def test_text_is_stripped_and_blank_is_refused():
    assert Assumption(id="a", statement="  claim  ").statement == "claim"
    with pytest.raises(InvalidTextError):
        Assumption(id="a", statement="   ")
    with pytest.raises(InvalidTextError):
        ResearchNote(id="n", question="")


def test_store_refuses_more_than_the_limit():
    store = NoteStore()
    note = store.create_note("q?")
    for i in range(MAX_ASSUMPTIONS_PER_NOTE):
        store.add_assumption(note.id, f"claim {i}")
    with pytest.raises(LimitError):
        store.add_assumption(note.id, "one too many")


def test_rejected_assumption_leaves_the_note_and_ids_untouched():
    store = NoteStore()
    note = store.create_note("q?")
    with pytest.raises(MissingSourceError):
        store.add_assumption(note.id, "claim", evidence=S)
    assert store.get_note(note.id).assumptions == ()
    _, added = store.add_assumption(note.id, "claim")
    assert added.id == "asm-1"
