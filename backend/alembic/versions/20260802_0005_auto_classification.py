"""automatic classification schema

Revision ID: 20260802_0005
Revises: 20260802_0004
Create Date: 2026-09-16

Classification audit snapshots contain identifiers and derived metadata only.
They must never contain original files, complete text, local paths, vectors,
raw model output, or API keys.
"""

from datetime import datetime
import re
from typing import Sequence, Union
import unicodedata

from alembic import op
import sqlalchemy as sa


revision: str = "20260802_0005"
down_revision: Union[str, None] = "20260802_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOP_CATEGORY_DESCRIPTIONS = {
    "工作与项目": "工作职责、项目资料、会议、计划与交付",
    "技术与工具": "软件、编程、系统、设备与工具使用",
    "学习与研究": "课程、论文、读书、知识与研究资料",
    "财务与法律": "账务、投资、合同、税务与法律资料",
    "健康与生活": "健康、家庭、日常生活与个人事务",
    "兴趣与收藏": "兴趣爱好、娱乐、旅行与收藏",
    "其他": "无法稳定归入以上分类的资料",
}


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _normalized_tag_name(tag_id: int, value: str) -> str:
    return _normalize_name(value) or f"tag-{tag_id}"


def _global_tag_name_unique_constraints() -> list[str]:
    return [
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("tags")
        if constraint.get("name")
        and constraint.get("column_names") == ["name"]
    ]


def _require_owned_tags() -> None:
    orphan = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM tags WHERE user_id IS NULL")
    ).scalar()
    if orphan:
        raise RuntimeError(
            f"tags.user_id contains NULL for {orphan} rows; ownership backfill required"
        )


def _backfill_and_merge_tags() -> None:
    conn = op.get_bind()
    tags = list(
        conn.execute(
            sa.text("SELECT id, user_id, name FROM tags ORDER BY user_id, id")
        ).mappings()
    )
    for tag in tags:
        conn.execute(
            sa.text(
                "UPDATE tags SET normalized_name = :normalized_name WHERE id = :tag_id"
            ),
            {
                "normalized_name": _normalized_tag_name(tag["id"], tag["name"]),
                "tag_id": tag["id"],
            },
        )

    ordered_tags = list(
        conn.execute(
            sa.text(
                "SELECT id, user_id, normalized_name FROM tags "
                "ORDER BY user_id, normalized_name, id"
            )
        ).mappings()
    )
    keep_by_key: dict[tuple[int, str], int] = {}
    for tag in ordered_tags:
        key = (tag["user_id"], tag["normalized_name"])
        keep_id = keep_by_key.setdefault(key, tag["id"])
        if keep_id == tag["id"]:
            continue
        _merge_tag_links(keep_id=keep_id, duplicate_id=tag["id"])
        conn.execute(
            sa.text("DELETE FROM tags WHERE id = :duplicate_id"),
            {"duplicate_id": tag["id"]},
        )


def _merge_tag_links(keep_id: int, duplicate_id: int) -> None:
    conn = op.get_bind()
    duplicate_links = list(
        conn.execute(
            sa.text(
                "SELECT id, document_id, created_at FROM document_tags "
                "WHERE tag_id = :duplicate_id ORDER BY id"
            ),
            {"duplicate_id": duplicate_id},
        ).mappings()
    )
    for duplicate_link in duplicate_links:
        keep_link = conn.execute(
            sa.text(
                "SELECT id, created_at FROM document_tags "
                "WHERE document_id = :document_id AND tag_id = :keep_id LIMIT 1"
            ),
            {
                "document_id": duplicate_link["document_id"],
                "keep_id": keep_id,
            },
        ).mappings().first()
        if keep_link is None:
            conn.execute(
                sa.text(
                    "UPDATE document_tags SET tag_id = :keep_id WHERE id = :link_id"
                ),
                {"keep_id": keep_id, "link_id": duplicate_link["id"]},
            )
            continue

        duplicate_created_at = duplicate_link["created_at"]
        keep_created_at = keep_link["created_at"]
        if duplicate_created_at is not None and (
            keep_created_at is None or duplicate_created_at < keep_created_at
        ):
            conn.execute(
                sa.text(
                    "UPDATE document_tags SET created_at = :created_at WHERE id = :link_id"
                ),
                {
                    "created_at": duplicate_created_at,
                    "link_id": keep_link["id"],
                },
            )
        conn.execute(
            sa.text("DELETE FROM document_tags WHERE id = :link_id"),
            {"link_id": duplicate_link["id"]},
        )


def _seed_top_categories() -> None:
    conn = op.get_bind()
    user_ids = list(
        conn.execute(
            sa.text("SELECT id FROM users WHERE id IS NOT NULL ORDER BY id")
        ).scalars()
    )
    category_table = sa.table(
        "categories",
        sa.column("user_id", sa.Integer()),
        sa.column("parent_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("normalized_name", sa.String()),
        sa.column("path_key", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_archived", sa.Boolean()),
        sa.column("created_by", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.utcnow()
    rows = [
        {
            "user_id": user_id,
            "parent_id": None,
            "name": name,
            "normalized_name": _normalize_name(name),
            "path_key": _normalize_name(name),
            "description": description,
            "is_system": True,
            "is_archived": False,
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
        }
        for user_id in user_ids
        for name, description in TOP_CATEGORY_DESCRIPTIONS.items()
    ]
    if rows:
        op.bulk_insert(category_table, rows)


def upgrade() -> None:
    _require_owned_tags()

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False),
        sa.Column("path_key", sa.String(220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by",
            sa.Enum("system", "llm", "user", name="category_created_by"),
            nullable=False,
            server_default="system",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_categories_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name="fk_categories_parent",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "user_id",
            "path_key",
            name="uq_categories_user_path_key",
        ),
    )
    op.create_index(
        "ix_categories_user_parent",
        "categories",
        ["user_id", "parent_id", "is_archived"],
    )

    op.create_table(
        "classification_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("classification_version", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("method", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("reverted_at", sa.DateTime(), nullable=True),
        sa.Column("reverted_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_classification_events_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_classification_events_document",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reverted_by_id"],
            ["classification_events.id"],
            name="fk_classification_events_reverted_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_classification_events_idempotency_key",
        ),
    )
    op.create_index(
        "ix_classification_events_user_created",
        "classification_events",
        ["user_id", "created_at", "id"],
    )

    op.add_column("documents", sa.Column("category_id", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "classification_status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "fallback",
                "failed",
                name="classification_status",
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "classification_method",
            sa.Enum("llm", "embedding", "user", "none", name="classification_method"),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column("documents", sa.Column("classification_confidence", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("classification_version", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("classification_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("classified_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("auto_summary", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_documents_category",
        "documents",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_user_category",
        "documents",
        ["user_id", "category_id"],
    )

    op.add_column("tags", sa.Column("normalized_name", sa.String(50), nullable=True))

    op.add_column(
        "document_tags",
        sa.Column(
            "source",
            sa.Enum("llm", "user", name="document_tag_source"),
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column("document_tags", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "document_tags",
        sa.Column("classification_event_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_tags_classification_event",
        "document_tags",
        "classification_events",
        ["classification_event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE document_tags SET source='user'")

    op.add_column("ingestion_jobs", sa.Column("available_at", sa.DateTime(), nullable=True))

    _backfill_and_merge_tags()
    for constraint_name in _global_tag_name_unique_constraints():
        op.drop_constraint(constraint_name, "tags", type_="unique")
    op.alter_column(
        "tags",
        "normalized_name",
        existing_type=sa.String(50),
        nullable=False,
    )
    op.alter_column(
        "tags",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_tags_user_normalized_name",
        "tags",
        ["user_id", "normalized_name"],
    )

    _seed_top_categories()
    op.execute(
        "UPDATE documents SET classification_status='pending', "
        "classification_method='none'"
    )


def downgrade() -> None:
    duplicate_name = op.get_bind().execute(
        sa.text(
            "SELECT name FROM tags GROUP BY name HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_name is not None:
        raise RuntimeError(
            "cannot restore global tags.name uniqueness while duplicate names exist across users"
        )

    op.drop_constraint("uq_tags_user_normalized_name", "tags", type_="unique")
    op.create_unique_constraint("uq_tags_name", "tags", ["name"])
    op.alter_column(
        "tags",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.drop_constraint(
        "fk_document_tags_classification_event",
        "document_tags",
        type_="foreignkey",
    )
    op.drop_column("document_tags", "classification_event_id")
    op.drop_column("document_tags", "confidence")
    op.drop_column("document_tags", "source")

    op.drop_index("ix_documents_user_category", table_name="documents")
    op.drop_constraint("fk_documents_category", "documents", type_="foreignkey")
    op.drop_column("documents", "auto_summary")
    op.drop_column("documents", "classified_at")
    op.drop_column("documents", "classification_error")
    op.drop_column("documents", "classification_version")
    op.drop_column("documents", "classification_confidence")
    op.drop_column("documents", "classification_method")
    op.drop_column("documents", "classification_status")
    op.drop_column("documents", "category_id")

    op.drop_column("ingestion_jobs", "available_at")

    op.drop_index(
        "ix_classification_events_user_created",
        table_name="classification_events",
    )
    op.drop_table("classification_events")
    op.drop_index("ix_categories_user_parent", table_name="categories")
    op.drop_table("categories")
    op.drop_column("tags", "normalized_name")
