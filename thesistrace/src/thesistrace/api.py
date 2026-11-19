"""HTTP API (FastAPI) over :class:`thesistrace.store.NoteStore`, plus the web front end.

Every response that carries a note also carries its freshly computed evidence summary,
so the page never has to work out what is proven on its own. Errors use one envelope:
``{"error": {"type": <code>, "message": ...}}``.

Run: ``python -m thesistrace.api`` (serves on 127.0.0.1:8000 with the sample note).
Without this server, the same page runs on its own in the browser (``assets/engine.js``).
"""

from pathlib import Path
from typing import Annotated, Any, Final

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from thesistrace.domain import (
    MAX_QUESTION_LENGTH,
    MAX_SOURCE_LENGTH,
    MAX_STATEMENT_LENGTH,
    MAX_TEXT_LENGTH,
    Assumption,
    Evidence,
    NotFoundError,
    ResearchNote,
    ThesisTraceError,
)
from thesistrace.scenario import seed
from thesistrace.store import NoteStore
from thesistrace.summary import summarize

HOST: Final = "127.0.0.1"
PORT: Final = 8000
HTTP_CREATED: Final = 201
HTTP_NO_CONTENT: Final = 204
HTTP_NOT_FOUND: Final = 404
HTTP_UNPROCESSABLE: Final = 422
# The page lives at the project root so GitHub Pages can serve the same files without
# this server (they fall back to assets/engine.js). Run from a checkout or editable install.
WEB_DIR: Final = Path(__file__).resolve().parents[2]

Question = Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_LENGTH)]
Statement = Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_LENGTH)]
LongText = Annotated[str, Field(max_length=MAX_TEXT_LENGTH)]
Source = Annotated[str | None, Field(max_length=MAX_SOURCE_LENGTH)]


class _Model(BaseModel):
    """Base for request bodies: unknown fields are rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")


class NoteIn(_Model):
    question: Question
    context: LongText = ""
    conclusion: LongText = ""


class NotePatch(_Model):
    question: Question | None = None
    context: LongText | None = None
    conclusion: LongText | None = None


class AssumptionIn(_Model):
    statement: Statement
    evidence: Evidence = Evidence.UNVERIFIED
    source: Source = None
    rationale: LongText = ""
    critical: StrictBool = False


class AssumptionPatch(_Model):
    statement: Statement | None = None
    evidence: Evidence | None = None
    source: Source = None  # sent as null clears the citation; omitted keeps it
    rationale: LongText | None = None
    critical: StrictBool | None = None


class AssumptionOut(BaseModel):
    id: str
    statement: str
    evidence: Evidence
    source: str | None
    rationale: str
    critical: bool


class SummaryOut(BaseModel):
    total: int
    counts: dict[Evidence, int]
    shares: dict[Evidence, int]
    verdict: str
    headline: str
    proven: list[str]
    uncertain: list[str]
    needs_source: list[str]
    critical_open: int


class NoteOut(BaseModel):
    id: str
    question: str
    context: str
    conclusion: str
    assumptions: list[AssumptionOut]
    summary: SummaryOut


class NoteListItem(BaseModel):
    id: str
    question: str
    verdict: str
    total: int


def _assumption_out(item: Assumption) -> AssumptionOut:
    return AssumptionOut(
        id=item.id,
        statement=item.statement,
        evidence=item.evidence,
        source=item.source,
        rationale=item.rationale,
        critical=item.critical,
    )


def note_out(note: ResearchNote) -> NoteOut:
    """Serialise a note together with its evidence summary."""
    summary = summarize(note)
    return NoteOut(
        id=note.id,
        question=note.question,
        context=note.context,
        conclusion=note.conclusion,
        assumptions=[_assumption_out(a) for a in note.assumptions],
        summary=SummaryOut(
            total=summary.total,
            counts=summary.counts,
            shares=summary.shares,
            verdict=summary.verdict.value,
            headline=summary.headline,
            proven=list(summary.proven),
            uncertain=list(summary.uncertain),
            needs_source=list(summary.needs_source),
            critical_open=summary.critical_open,
        ),
    )


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"type": code, "message": message}})


def create_app(store: NoteStore | None = None) -> FastAPI:
    """Build the app around ``store`` (a fresh, empty store when omitted)."""
    notes = store if store is not None else NoteStore()
    app = FastAPI(
        title="ThesisTrace",
        summary="Make the reasoning behind a financial conclusion visible before it is trusted.",
        version="1.0.0",
    )

    @app.exception_handler(ThesisTraceError)
    async def _domain_error(_: Request, exc: ThesisTraceError) -> JSONResponse:
        status = HTTP_NOT_FOUND if isinstance(exc, NotFoundError) else HTTP_UNPROCESSABLE
        return _error(status, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first: dict[str, Any] = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else "invalid request"
        return _error(HTTP_UNPROCESSABLE, "invalid_request", message)

    @app.get("/api/notes")
    def list_notes() -> list[NoteListItem]:
        items = []
        for note in notes.list_notes():
            summary = summarize(note)
            items.append(
                NoteListItem(
                    id=note.id,
                    question=note.question,
                    verdict=summary.verdict.value,
                    total=summary.total,
                )
            )
        return items

    @app.post("/api/notes", status_code=HTTP_CREATED)
    def create_note(body: NoteIn) -> NoteOut:
        return note_out(notes.create_note(body.question, body.context, body.conclusion))

    @app.get("/api/notes/{note_id}")
    def get_note(note_id: str) -> NoteOut:
        return note_out(notes.get_note(note_id))

    @app.patch("/api/notes/{note_id}")
    def update_note(note_id: str, body: NotePatch) -> NoteOut:
        return note_out(
            notes.update_note(
                note_id, question=body.question, context=body.context, conclusion=body.conclusion
            )
        )

    @app.delete("/api/notes/{note_id}", status_code=HTTP_NO_CONTENT)
    def delete_note(note_id: str) -> Response:
        notes.delete_note(note_id)
        return Response(status_code=HTTP_NO_CONTENT)

    @app.get("/api/notes/{note_id}/summary")
    def get_summary(note_id: str) -> SummaryOut:
        return note_out(notes.get_note(note_id)).summary

    @app.post("/api/notes/{note_id}/assumptions", status_code=HTTP_CREATED)
    def add_assumption(note_id: str, body: AssumptionIn) -> NoteOut:
        note, _ = notes.add_assumption(
            note_id,
            body.statement,
            evidence=body.evidence,
            source=body.source,
            rationale=body.rationale,
            critical=body.critical,
        )
        return note_out(note)

    @app.patch("/api/notes/{note_id}/assumptions/{assumption_id}")
    def update_assumption(note_id: str, assumption_id: str, body: AssumptionPatch) -> NoteOut:
        changes: dict[str, Any] = {
            "statement": body.statement,
            "evidence": body.evidence,
            "rationale": body.rationale,
            "critical": body.critical,
        }
        if "source" in body.model_fields_set:
            changes["source"] = body.source
        note, _ = notes.update_assumption(note_id, assumption_id, **changes)
        return note_out(note)

    @app.delete("/api/notes/{note_id}/assumptions/{assumption_id}")
    def remove_assumption(note_id: str, assumption_id: str) -> NoteOut:
        return note_out(notes.remove_assumption(note_id, assumption_id))

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
    return app


def main() -> None:
    """Serve the app locally with the sample note loaded."""
    store = NoteStore()
    seed(store)
    uvicorn.run(create_app(store), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
