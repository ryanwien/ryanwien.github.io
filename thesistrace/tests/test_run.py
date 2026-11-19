"""The end-to-end run: the sample note, its summary, and byte-identical ``results/``."""

import json
from pathlib import Path

import pytest

from thesistrace import run
from thesistrace.scenario import ASSUMPTIONS, seed
from thesistrace.store import NoteStore
from thesistrace.summary import Verdict, summarize


def test_sample_note_uses_every_label_and_is_blocked():
    note = seed(NoteStore())
    summary = summarize(note)
    assert summary.total == len(ASSUMPTIONS)
    assert all(summary.counts.values())
    assert summary.verdict is Verdict.BLOCKED


def test_run_writes_identical_results_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run, "RESULTS_DIR", tmp_path)
    run.main()
    first = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}
    run.main()
    second = {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}
    assert set(first) == {"metrics.json", "REPORT.md"}
    assert first == second

    metrics = json.loads(first["metrics.json"])
    assert metrics["verdict"] == "blocked"
    assert metrics["counts"] == {"supported": 2, "mixed": 1, "unverified": 2}
    # One of each label after three assumptions: the spare point goes to supported.
    assert metrics["supported_share_as_built"] == [100, 50, 34, 50, 40]
    assert metrics["tests"] == run.count_tests()
