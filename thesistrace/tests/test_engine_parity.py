"""The in-browser engine (assets/engine.js) must agree with the Python package.

The static site runs on engine.js alone, so any drift from the server's rules would show
reviewers a different verdict depending on where they opened the page. These tests run
the engine under Node and compare it with Python on the same inputs. They skip when Node
is not installed.
"""

import json
import shutil
import subprocess
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from thesistrace.domain import Assumption, Evidence, ResearchNote
from thesistrace.scenario import ASSUMPTIONS, CONCLUSION, CONTEXT, QUESTION
from thesistrace.summary import summarize

ENGINE = Path(__file__).resolve().parents[1] / "assets" / "engine.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

# Reads {"mode": ..., ...} on stdin and prints JSON results.
RUNNER = r"""
const E = require(process.argv[1]);
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
let out;
if (input.mode === "summaries") {
  out = input.notes.map((note) => E.summarize(note));
} else if (input.mode === "sample") {
  out = E.createEngine().request("GET", "api/notes/note-1");
} else {
  const engine = E.createEngine(undefined, { seed: false });
  out = input.ops.map(([method, path, body]) => {
    try {
      return { status: 200, body: engine.request(method, path, body) };
    } catch (err) {
      if (!(err instanceof E.EngineError)) throw err;
      return { status: err.status, type: err.code };
    }
  });
}
process.stdout.write(JSON.stringify(out));
"""


def run_engine(payload: dict[str, Any]) -> Any:
    done = subprocess.run(
        [NODE, "-e", RUNNER, str(ENGINE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


def python_summary(note: ResearchNote) -> dict[str, Any]:
    s = summarize(note)
    return {
        "total": s.total,
        "counts": {label.value: s.counts[label] for label in Evidence},
        "shares": {label.value: s.shares[label] for label in Evidence},
        "verdict": s.verdict.value,
        "headline": s.headline,
        "proven": list(s.proven),
        "uncertain": list(s.uncertain),
        "needs_source": list(s.needs_source),
        "critical_open": s.critical_open,
    }


def test_summaries_match_for_every_small_note():
    options = list(product(Evidence, (False, True)))
    notes = [()]
    for size in (1, 2, 3):
        notes += list(product(options, repeat=size))
    # Larger notes stress the percentage rounding.
    notes += [
        tuple(
            (label, i % 3 == 0) for label, n in zip(Evidence, split, strict=True) for i in range(n)
        )
        for split in product(range(8), repeat=3)
        if sum(split) > 3
    ]
    py_notes = [
        ResearchNote(
            id="n",
            question="q?",
            assumptions=tuple(
                Assumption(
                    id=f"a{i}",
                    statement=f"claim {i}",
                    evidence=evidence,
                    source=None if evidence is Evidence.UNVERIFIED else "src",
                    critical=critical,
                )
                for i, (evidence, critical) in enumerate(spec)
            ),
        )
        for spec in notes
    ]
    js_notes = [
        {
            "assumptions": [
                {"id": a.id, "evidence": a.evidence.value, "critical": a.critical}
                for a in note.assumptions
            ]
        }
        for note in py_notes
    ]
    expected = [python_summary(note) for note in py_notes]
    assert run_engine({"mode": "summaries", "notes": js_notes}) == expected


def test_sample_note_matches_the_python_scenario():
    note = run_engine({"mode": "sample"})
    assert (note["question"], note["context"], note["conclusion"]) == (
        QUESTION,
        CONTEXT,
        CONCLUSION,
    )
    got = [
        (a["statement"], a["evidence"], a["source"], a["rationale"], a["critical"])
        for a in note["assumptions"]
    ]
    assert got == [(s, e.value, src, r, c) for s, e, src, r, c in ASSUMPTIONS]


OPS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("POST", "api/notes", {"question": "  Can margins hold?  ", "context": "Retailer"}),
    ("POST", "api/notes/note-1/assumptions", {"statement": "Wages flat", "critical": True}),
    ("POST", "api/notes/note-1/assumptions", {"statement": "Rents fall", "evidence": "supported"}),
    (
        "POST",
        "api/notes/note-1/assumptions",
        {"statement": "Rents fall", "evidence": "supported", "source": " Lease filings "},
    ),
    ("PATCH", "api/notes/note-1/assumptions/asm-1", {"evidence": "mixed"}),
    ("PATCH", "api/notes/note-1/assumptions/asm-1", {"evidence": "mixed", "source": "BLS"}),
    ("PATCH", "api/notes/note-1/assumptions/asm-1", {"source": None}),
    ("PATCH", "api/notes/note-1/assumptions/asm-1", {"rationale": "Two series disagree"}),
    ("PATCH", "api/notes/note-1/assumptions/asm-1", {"evidence": "unverified", "source": None}),
    ("PATCH", "api/notes/note-1", {"conclusion": "Probably", "question": None}),
    ("GET", "api/notes/note-1/summary", None),
    ("POST", "api/notes/note-1/assumptions", {"statement": "   "}),
    ("POST", "api/notes/note-1/assumptions", {"statement": "x", "evidence": "likely"}),
    ("POST", "api/notes/note-1/assumptions", {"statement": "x", "confidence": 1}),
    ("POST", "api/notes/note-1/assumptions", {"statement": "Tax rate steady"}),
    ("DELETE", "api/notes/note-1/assumptions/asm-1", None),
    ("GET", "api/notes", None),
    ("GET", "api/notes/note-9", None),
    ("PATCH", "api/notes/note-1/assumptions/asm-99", {}),
    ("DELETE", "api/notes/note-1", None),
    ("GET", "api/notes", None),
]


def _server_result(client: TestClient, method: str, path: str, body: Any) -> dict[str, Any]:
    response = client.request(method, f"/{path}", json=body)
    if response.status_code >= 400:
        return {"status": response.status_code, "type": response.json()["error"]["type"]}
    payload = None if response.status_code == 204 else response.json()
    return {"status": 200, "body": payload}


def test_same_requests_give_the_same_answers(client: TestClient):
    expected = [_server_result(client, *op) for op in OPS]
    got = run_engine({"mode": "ops", "ops": OPS})
    for op, want, have in zip(OPS, expected, got, strict=True):
        assert have == want, op
