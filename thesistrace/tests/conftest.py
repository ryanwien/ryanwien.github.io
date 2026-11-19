"""Shared fixtures: an empty store, an API client over it, and a note-making helper."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from thesistrace.api import create_app
from thesistrace.store import NoteStore

MakeNote = Callable[..., dict[str, Any]]


@pytest.fixture
def store() -> NoteStore:
    return NoteStore()


@pytest.fixture
def client(store: NoteStore) -> Iterator[TestClient]:
    with TestClient(create_app(store)) as test_client:
        yield test_client


@pytest.fixture
def make_note(client: TestClient) -> MakeNote:
    """``make_note(question=..., **fields)`` creates a note over the API and returns it."""

    def _make(question: str = "Will margins hold next year?", **fields: Any) -> dict[str, Any]:
        response = client.post("/api/notes", json={"question": question, **fields})
        assert response.status_code == 201, response.text
        return response.json()

    return _make
