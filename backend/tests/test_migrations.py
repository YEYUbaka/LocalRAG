"""Alembic migration tests.

These verify the versioned schema contract without a live MySQL:
the revision chain exists, is additive, and the readiness gate logic
rejects revision drift.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, JSON, String, Text, UniqueConstraint

from app.domain.tenant import TenantScope
import app.models as models


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIGRATION_PATH = VERSIONS_DIR / "20260802_0005_auto_classification.py"


def unique_column_sets(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def unique_constraint_names(table):
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def foreign_key(column):
    keys = list(column.foreign_keys)
    assert len(keys) == 1
    return keys[0]


def load_auto_classification_migration():
    assert MIGRATION_PATH.exists(), "automatic classification migration is missing"
    spec = importlib.util.spec_from_file_location("auto_classification_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_revisions_chain_is_linear_and_ordered():
    revisions = sorted(p.stem for p in VERSIONS_DIR.glob("*.py") if p.stem != "__init__")
    assert revisions == [
        "20260802_0001_baseline",
        "20260802_0002_tenant_expand",
        "20260802_0003_ingestion_jobs",
        "20260802_0004_chunk_identity",
        "20260802_0005_auto_classification",
    ]

    migration = load_auto_classification_migration()
    assert migration.revision == "20260802_0005"
    assert migration.down_revision == "20260802_0004"


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
    assert hasattr(models, "Category")
    assert hasattr(models, "ClassificationEvent")


def test_document_md5_uniqueness_is_tenant_scoped():
    assert not models.Document.__table__.c.md5_hash.unique
    unique_columns = unique_column_sets(models.Document.__table__)
    assert ("user_id", "kb_id", "md5_hash") in unique_columns


def test_document_has_stable_chunk_identity_fields():
    assert models.Document.__table__.c.document_key.nullable
    assert not models.Document.__table__.c.document_version.nullable
    assert not models.Document.__table__.c.chunker_version.nullable


def test_category_model_matches_frozen_schema():
    table = models.Category.__table__
    assert isinstance(table.c.id.type, Integer)
    assert not table.c.user_id.nullable
    assert foreign_key(table.c.user_id).target_fullname == "users.id"
    assert foreign_key(table.c.user_id).ondelete == "CASCADE"
    assert table.c.parent_id.nullable
    assert foreign_key(table.c.parent_id).target_fullname == "categories.id"
    assert foreign_key(table.c.parent_id).ondelete == "RESTRICT"
    assert table.c.name.type.length == 100
    assert table.c.normalized_name.type.length == 100
    assert table.c.path_key.type.length == 220
    assert isinstance(table.c.description.type, Text)
    assert isinstance(table.c.is_system.type, Boolean)
    assert isinstance(table.c.is_archived.type, Boolean)
    assert isinstance(table.c.created_by.type, Enum)
    assert table.c.created_by.type.name == "category_created_by"
    assert tuple(table.c.created_by.type.enums) == ("system", "llm", "user")
    assert not table.c.created_at.nullable
    assert not table.c.updated_at.nullable
    assert ("user_id", "path_key") in unique_column_sets(table)
    assert "uq_categories_user_path_key" in unique_constraint_names(table)
    index = next(index for index in table.indexes if index.name == "ix_categories_user_parent")
    assert tuple(column.name for column in index.columns) == ("user_id", "parent_id", "is_archived")


def test_classification_event_model_matches_frozen_schema():
    table = models.ClassificationEvent.__table__
    expected_types = {
        "id": Integer,
        "user_id": Integer,
        "document_id": Integer,
        "event_type": String,
        "before_state": JSON,
        "after_state": JSON,
        "document_version": Integer,
        "classification_version": String,
        "prompt_version": String,
        "model_name": String,
        "method": String,
        "confidence": Float,
        "error_code": String,
        "llm_call_count": Integer,
        "idempotency_key": String,
        "reverted_at": DateTime,
        "reverted_by_id": Integer,
        "created_at": DateTime,
    }
    for name, expected_type in expected_types.items():
        assert isinstance(table.c[name].type, expected_type)
    assert not table.c.user_id.nullable
    assert foreign_key(table.c.user_id).ondelete == "CASCADE"
    assert table.c.document_id.nullable
    assert foreign_key(table.c.document_id).ondelete == "SET NULL"
    assert foreign_key(table.c.reverted_by_id).ondelete == "SET NULL"
    assert not table.c.event_type.nullable
    assert not table.c.classification_version.nullable
    assert not table.c.llm_call_count.nullable
    assert not table.c.created_at.nullable
    assert ("idempotency_key",) in unique_column_sets(table)
    assert "uq_classification_events_idempotency_key" in unique_constraint_names(table)
    index = next(index for index in table.indexes if index.name == "ix_classification_events_user_created")
    assert tuple(column.name for column in index.columns) == ("user_id", "created_at", "id")


def test_document_classification_fields_match_frozen_schema():
    table = models.Document.__table__
    assert table.c.category_id.nullable
    assert foreign_key(table.c.category_id).target_fullname == "categories.id"
    assert foreign_key(table.c.category_id).ondelete == "SET NULL"
    assert tuple(table.c.classification_status.type.enums) == (
        "pending", "running", "completed", "fallback", "failed"
    )
    assert tuple(table.c.classification_method.type.enums) == ("llm", "embedding", "user", "none")
    assert not table.c.classification_status.nullable
    assert not table.c.classification_method.nullable
    assert table.c.classification_confidence.nullable
    assert table.c.classification_version.type.length == 32
    assert isinstance(table.c.classification_error.type, Text)
    assert isinstance(table.c.classified_at.type, DateTime)
    assert isinstance(table.c.auto_summary.type, Text)
    index = next(index for index in table.indexes if index.name == "ix_documents_user_category")
    assert tuple(column.name for column in index.columns) == ("user_id", "category_id")


def test_tag_and_document_tag_models_match_frozen_schema():
    tag_table = models.Tag.__table__
    assert not tag_table.c.user_id.nullable
    assert not tag_table.c.name.unique
    assert not tag_table.c.normalized_name.nullable
    assert tag_table.c.normalized_name.type.length == 50
    assert ("user_id", "normalized_name") in unique_column_sets(tag_table)
    assert "uq_tags_user_normalized_name" in unique_constraint_names(tag_table)

    link_table = models.DocumentTag.__table__
    assert tuple(link_table.c.source.type.enums) == ("llm", "user")
    assert link_table.c.source.type.name == "document_tag_source"
    assert not link_table.c.source.nullable
    assert isinstance(link_table.c.confidence.type, Float)
    assert link_table.c.classification_event_id.nullable
    assert foreign_key(link_table.c.classification_event_id).target_fullname == "classification_events.id"
    assert foreign_key(link_table.c.classification_event_id).ondelete == "SET NULL"


def test_classification_relationships_are_declared():
    category_targets = {relationship.entity.class_ for relationship in models.Category.__mapper__.relationships}
    document_targets = {relationship.entity.class_ for relationship in models.Document.__mapper__.relationships}
    event_targets = {relationship.entity.class_ for relationship in models.ClassificationEvent.__mapper__.relationships}
    link_targets = {relationship.entity.class_ for relationship in models.DocumentTag.__mapper__.relationships}
    assert {models.Category, models.Document}.issubset(category_targets)
    assert {models.Category, models.ClassificationEvent}.issubset(document_targets)
    assert {models.Document, models.ClassificationEvent}.issubset(event_targets)
    assert models.ClassificationEvent in link_targets


def test_migration_normalization_matches_domain_algorithm():
    migration = load_auto_classification_migration()
    assert migration._normalize_name("  Ｐｙｔｈｏｎ\t 入门  ") == "python 入门"
    assert migration._normalized_tag_name(7, " \t ") == "tag-7"


def test_migration_contains_data_preservation_and_downgrade_guards():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ORDER BY user_id, normalized_name, id" in source
    assert "source='user'" in source or 'source = \'user\'' in source
    assert "tags.user_id contains NULL" in source
    assert "cannot restore global tags.name uniqueness" in source
    assert "op.drop_table(\"classification_events\")" in source
    assert "op.drop_table(\"categories\")" in source
    assert "DELETE FROM documents" not in source
    assert "DELETE FROM tags WHERE id = :duplicate_id" in source
