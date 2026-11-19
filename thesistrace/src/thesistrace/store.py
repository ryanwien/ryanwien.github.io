"""In-memory note store: the single place notes are created, changed and removed.

Invariants:

- Ids are sequential (``note-1``, ``asm-1``) and never reused, so runs are reproducible
  and a deleted id cannot silently point at a different note later.
- Every change replaces a whole immutable :class:`ResearchNote` under one lock, so a
  reader never sees a half-applied edit.
- Domain validation runs before the swap; a rejected change leaves the note untouched.
"""

import threading
from dataclasses import replace
from itertools import count

from thesistrace.domain import (
    MAX_ASSUMPTIONS_PER_NOTE,
    Assumption,
    Evidence,
    LimitError,
    NotFoundError,
    ResearchNote,
)

_UNSET = object()


class NoteStore:
    """Thread-safe, process-local store of research notes."""

    def __init__(self) -> None:
        self._notes: dict[str, ResearchNote] = {}
        self._lock = threading.Lock()
        self._note_ids = count(1)
        self._assumption_ids = count(1)

    def list_notes(self) -> list[ResearchNote]:
        """All notes, oldest first."""
        with self._lock:
            return list(self._notes.values())

    def get_note(self, note_id: str) -> ResearchNote:
        """The note with ``note_id`` or :class:`NotFoundError`."""
        with self._lock:
            return self._get(note_id)

    def create_note(self, question: str, context: str = "", conclusion: str = "") -> ResearchNote:
        """Create and store a new note with no assumptions."""
        with self._lock:
            note = ResearchNote(
                id=f"note-{next(self._note_ids)}",
                question=question,
                context=context,
                conclusion=conclusion,
            )
            self._notes[note.id] = note
            return note

    def update_note(
        self,
        note_id: str,
        *,
        question: str | None = None,
        context: str | None = None,
        conclusion: str | None = None,
    ) -> ResearchNote:
        """Change the note's text fields; ``None`` leaves a field as it is."""
        with self._lock:
            note = self._get(note_id)
            changes = {
                key: value
                for key, value in (
                    ("question", question),
                    ("context", context),
                    ("conclusion", conclusion),
                )
                if value is not None
            }
            updated = replace(note, **changes)
            self._notes[note_id] = updated
            return updated

    def delete_note(self, note_id: str) -> None:
        """Remove a note and its assumptions."""
        with self._lock:
            self._get(note_id)
            del self._notes[note_id]

    def add_assumption(
        self,
        note_id: str,
        statement: str,
        *,
        evidence: Evidence = Evidence.UNVERIFIED,
        source: str | None = None,
        rationale: str = "",
        critical: bool = False,
    ) -> tuple[ResearchNote, Assumption]:
        """Append an assumption to a note; returns the updated note and the assumption."""
        with self._lock:
            note = self._get(note_id)
            if len(note.assumptions) >= MAX_ASSUMPTIONS_PER_NOTE:
                raise LimitError(f"a note holds at most {MAX_ASSUMPTIONS_PER_NOTE} assumptions")
            # Validate before drawing an id, so a rejected assumption burns no id.
            draft = Assumption(
                id="draft",
                statement=statement,
                evidence=evidence,
                source=source,
                rationale=rationale,
                critical=critical,
            )
            item = replace(draft, id=f"asm-{next(self._assumption_ids)}")
            updated = replace(note, assumptions=(*note.assumptions, item))
            self._notes[note_id] = updated
            return updated, item

    def update_assumption(
        self,
        note_id: str,
        assumption_id: str,
        *,
        statement: str | None = None,
        evidence: Evidence | None = None,
        source: object = _UNSET,
        rationale: str | None = None,
        critical: bool | None = None,
    ) -> tuple[ResearchNote, Assumption]:
        """Change one assumption. ``source=None`` clears the citation; omit it to keep it."""
        with self._lock:
            note = self._get(note_id)
            current = note.assumption(assumption_id)
            changes: dict[str, object] = {
                key: value
                for key, value in (
                    ("statement", statement),
                    ("evidence", evidence),
                    ("rationale", rationale),
                    ("critical", critical),
                )
                if value is not None
            }
            if source is not _UNSET:
                changes["source"] = source
            item = replace(current, **changes)
            updated = replace(
                note,
                assumptions=tuple(item if a.id == assumption_id else a for a in note.assumptions),
            )
            self._notes[note_id] = updated
            return updated, item

    def remove_assumption(self, note_id: str, assumption_id: str) -> ResearchNote:
        """Delete one assumption from a note."""
        with self._lock:
            note = self._get(note_id)
            note.assumption(assumption_id)
            updated = replace(
                note, assumptions=tuple(a for a in note.assumptions if a.id != assumption_id)
            )
            self._notes[note_id] = updated
            return updated

    def _get(self, note_id: str) -> ResearchNote:
        try:
            return self._notes[note_id]
        except KeyError:
            raise NotFoundError(f"note {note_id} not found") from None
