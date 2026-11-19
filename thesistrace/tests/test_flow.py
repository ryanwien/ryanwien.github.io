"""The core flow over HTTP: research note -> assumptions -> evidence summary."""

from conftest import MakeNote
from fastapi.testclient import TestClient


def _add(client: TestClient, note_id: str, **body: object) -> dict:
    response = client.post(f"/api/notes/{note_id}/assumptions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_note_starts_empty_with_an_empty_summary(make_note: MakeNote):
    note = make_note("Can the lender keep its dividend?", context="Regional bank")
    assert note["question"] == "Can the lender keep its dividend?"
    assert note["assumptions"] == []
    summary = note["summary"]
    assert summary["verdict"] == "empty"
    assert summary["total"] == 0
    assert summary["shares"] == {"supported": 0, "mixed": 0, "unverified": 0}


def test_full_flow_from_note_to_reviewable_summary(client: TestClient, make_note: MakeNote):
    note = make_note("Can the lender keep its dividend?")
    nid = note["id"]

    # 1. An unverified, load-bearing assumption blocks the verdict.
    note = _add(client, nid, statement="Deposits stay flat", critical=True)
    deposits = note["assumptions"][0]["id"]
    assert note["summary"]["verdict"] == "blocked"
    assert note["summary"]["needs_source"] == [deposits]
    assert note["summary"]["critical_open"] == 1

    # 2. A sourced, supported assumption is proven.
    note = _add(
        client,
        nid,
        statement="Capital ratio above 12%",
        evidence="supported",
        source="Q3 call report, schedule RC-R",
    )
    capital = note["assumptions"][1]["id"]
    assert note["summary"]["proven"] == [capital]
    assert note["summary"]["verdict"] == "blocked"

    # 3. Finding a source for the load-bearing one, but it is mixed: contested.
    response = client.patch(
        f"/api/notes/{nid}/assumptions/{deposits}",
        json={"evidence": "mixed", "source": "FDIC deposit data, 2025"},
    )
    assert response.status_code == 200, response.text
    note = response.json()
    assert note["summary"]["verdict"] == "contested"
    assert note["summary"]["uncertain"] == [deposits]
    assert note["summary"]["needs_source"] == []
    assert note["summary"]["counts"] == {"supported": 1, "mixed": 1, "unverified": 0}
    assert note["summary"]["shares"] == {"supported": 50, "mixed": 50, "unverified": 0}

    # 4. Firmer evidence: everything supported.
    note = client.patch(
        f"/api/notes/{nid}/assumptions/{deposits}", json={"evidence": "supported"}
    ).json()
    assert note["summary"]["verdict"] == "supported"
    assert note["summary"]["proven"] == [deposits, capital]  # load-bearing first

    # 5. The summary endpoint and the list agree with the note.
    summary = client.get(f"/api/notes/{nid}/summary").json()
    assert summary == note["summary"]
    listed = client.get("/api/notes").json()
    assert listed == [{"id": nid, "question": note["question"], "verdict": "supported", "total": 2}]


def test_supported_without_a_source_is_refused(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    response = client.post(
        f"/api/notes/{nid}/assumptions", json={"statement": "Rates fall", "evidence": "supported"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "missing_source"
    assert client.get(f"/api/notes/{nid}").json()["assumptions"] == []


def test_relabelling_to_mixed_without_a_source_is_refused(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    aid = _add(client, nid, statement="Rates fall")["assumptions"][0]["id"]
    response = client.patch(f"/api/notes/{nid}/assumptions/{aid}", json={"evidence": "mixed"})
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "missing_source"
    after = client.get(f"/api/notes/{nid}").json()
    assert after["assumptions"][0]["evidence"] == "unverified"


def test_clearing_the_source_of_supported_evidence_is_refused(
    client: TestClient, make_note: MakeNote
):
    nid = make_note()["id"]
    note = _add(client, nid, statement="Rates fall", evidence="supported", source="Fed minutes")
    aid = note["assumptions"][0]["id"]
    response = client.patch(f"/api/notes/{nid}/assumptions/{aid}", json={"source": None})
    assert response.status_code == 422
    assert client.get(f"/api/notes/{nid}").json()["assumptions"][0]["source"] == "Fed minutes"


def test_downgrading_to_unverified_then_clearing_the_source(
    client: TestClient, make_note: MakeNote
):
    nid = make_note()["id"]
    note = _add(client, nid, statement="Rates fall", evidence="supported", source="Fed minutes")
    aid = note["assumptions"][0]["id"]
    note = client.patch(
        f"/api/notes/{nid}/assumptions/{aid}", json={"evidence": "unverified", "source": None}
    ).json()
    assert note["assumptions"][0]["source"] is None
    assert note["summary"]["needs_source"] == [aid]
    assert note["summary"]["verdict"] == "needs_sources"


def test_omitting_source_in_a_patch_keeps_it(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    note = _add(client, nid, statement="Rates fall", evidence="mixed", source="Fed minutes")
    aid = note["assumptions"][0]["id"]
    note = client.patch(
        f"/api/notes/{nid}/assumptions/{aid}", json={"rationale": "Two members dissented"}
    ).json()
    assert note["assumptions"][0]["source"] == "Fed minutes"
    assert note["assumptions"][0]["rationale"] == "Two members dissented"


def test_removing_the_last_unverified_assumption_lifts_the_block(
    client: TestClient, make_note: MakeNote
):
    nid = make_note()["id"]
    _add(client, nid, statement="Sourced", evidence="supported", source="10-K p. 3")
    note = _add(client, nid, statement="Guess", critical=True)
    guess = note["assumptions"][1]["id"]
    assert note["summary"]["verdict"] == "blocked"
    response = client.delete(f"/api/notes/{nid}/assumptions/{guess}")
    assert response.status_code == 200
    assert response.json()["summary"]["verdict"] == "supported"


def test_editing_the_note_keeps_its_assumptions(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    _add(client, nid, statement="Volumes hold")
    note = client.patch(
        f"/api/notes/{nid}", json={"conclusion": "Probably, if volumes hold"}
    ).json()
    assert note["conclusion"] == "Probably, if volumes hold"
    assert len(note["assumptions"]) == 1


def test_deleting_a_note(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    assert client.delete(f"/api/notes/{nid}").status_code == 204
    response = client.get(f"/api/notes/{nid}")
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"


def test_unknown_ids_are_404(client: TestClient, make_note: MakeNote):
    nid = make_note()["id"]
    assert client.get("/api/notes/note-999").status_code == 404
    assert client.post("/api/notes/note-999/assumptions", json={"statement": "x"}).status_code == (
        404
    )
    assert client.patch(f"/api/notes/{nid}/assumptions/asm-999", json={}).status_code == 404
    assert client.delete(f"/api/notes/{nid}/assumptions/asm-999").status_code == 404


def test_request_validation_uses_the_error_envelope(client: TestClient, make_note: MakeNote):
    assert client.post("/api/notes", json={"question": ""}).json()["error"]["type"] == (
        "invalid_request"
    )
    nid = make_note()["id"]
    bad_label = client.post(
        f"/api/notes/{nid}/assumptions", json={"statement": "x", "evidence": "probably"}
    )
    assert bad_label.status_code == 422
    unknown_field = client.post(
        f"/api/notes/{nid}/assumptions", json={"statement": "x", "confidence": 0.9}
    )
    assert unknown_field.status_code == 422
    stringy_bool = client.post(
        f"/api/notes/{nid}/assumptions", json={"statement": "x", "critical": "yes"}
    )
    assert stringy_bool.status_code == 422


def test_whitespace_only_question_is_refused(client: TestClient):
    response = client.post("/api/notes", json={"question": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "invalid_text"


def test_front_end_is_served(client: TestClient):
    page = client.get("/")
    assert page.status_code == 200
    assert "ThesisTrace" in page.text
    assert "does not give financial" in page.text
    for asset in ("/assets/app.js", "/assets/styles.css", "/assets/engine.js"):
        assert client.get(asset).status_code == 200
