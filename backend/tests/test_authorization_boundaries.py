"""Cross-owner (IDOR) authorization boundary tests.

Uses isolated in-memory mocks so the suite is deterministic and requires
no real MySQL. The key contract: every owner mismatch returns 404 and
creates no side effects.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.application.access_policy import AccessPolicy
from app.domain.tenant import TenantScope


class _FakeSession:
    """Minimal fake ORM session supporting .query().filter().first()."""

    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *criteria):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


def _make_row(owner_id):
    return SimpleNamespace(id=1, user_id=owner_id)


def test_require_kb_returns_scope_for_owner():
    db = _FakeSession([_make_row(7)])
    scope = AccessPolicy.require_kb(db, 7, 1)
    assert scope == TenantScope(user_id=7, kb_id=1)


def test_require_kb_404_for_cross_owner():
    db = _FakeSession([])
    with pytest.raises(HTTPException) as caught:
        AccessPolicy.require_kb(db, 8, 1)
    assert caught.value.status_code == 404


@pytest.mark.parametrize("method", ["require_document", "require_conversation", "require_tag"])
def test_all_require_helpers_404_for_cross_owner(method):
    db = _FakeSession([])
    with pytest.raises(HTTPException) as caught:
        getattr(AccessPolicy, method)(db, 8, 1)
    assert caught.value.status_code == 404


def test_require_document_returns_owner_document():
    row = SimpleNamespace(id=5, user_id=7, filename="a.pdf")
    db = _FakeSession([row])
    doc = AccessPolicy.require_document(db, 7, 5)
    assert doc.id == 5
    assert doc.filename == "a.pdf"
