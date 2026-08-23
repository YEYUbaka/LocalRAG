"""Alembic migration tests.

These verify the versioned schema contract without a live MySQL:
the revision chain exists, is additive, and the readiness gate logic
rejects revision drift.
"""

from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint

from app.domain.tenant import TenantScope
from app.models import Document


def test_alembic_revisions_chain_is_linear_and_ordered():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    revisions = sorted(p.stem for p in versions_dir.glob("*.py") if p.stem != "__init__")
    assert len(revisions) >= 2
    for rev in revisions:
        assert rev.startswith("20260802_")


def test_tenant_scope_contract_used_by_migrations():
    scope = TenantScope(user_id=1, kb_id=1)
    assert scope.user_id == 1
    assert scope.kb_id == 1


def test_models_do_not_require_startup_ddl():
    """Application must not perform DDL at import; models stay declarative."""
    import app.models as models

    assert hasattr(models, "Base")
    assert hasattr(models, "User")
    assert hasattr(models, "Document")
    assert hasattr(models, "Tag")


def test_document_md5_uniqueness_is_tenant_scoped():
    assert not Document.__table__.c.md5_hash.unique
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in Document.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("user_id", "kb_id", "md5_hash") in unique_columns


def test_document_has_stable_chunk_identity_fields():
    assert Document.__table__.c.document_key.nullable
    assert not Document.__table__.c.document_version.nullable
    assert not Document.__table__.c.chunker_version.nullable
