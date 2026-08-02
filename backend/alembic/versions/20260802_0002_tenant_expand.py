"""tenant expand: ownership backfill and indexes

Revision ID: 20260802_0002
Revises: 20260802_0001
Create Date: 2026-08-02

Additive ownership migration. Legacy owner is selected only when exactly
one user exists; ambiguity fails closed with RuntimeError.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260802_0002"
down_revision: Union[str, None] = "20260802_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _select_legacy_owner() -> int | None:
    conn = op.get_bind()
    user_count = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
    if user_count == 0:
        return None
    if user_count > 1:
        # Check for orphan rows that would need backfill
        for table in ("documents", "knowledge_bases", "conversations", "tags"):
            orphan = conn.execute(
                sa.text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")
            ).scalar()
            if orphan > 0:
                raise RuntimeError(
                    f"{table} has {orphan} orphan rows with multiple users; "
                    "manual ownership backfill required"
                )
        return None
    return conn.execute(sa.text("SELECT id FROM users LIMIT 1")).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Ensure ownership columns exist on all tables
    inspector = sa.inspect(conn)
    for table in ("documents", "knowledge_bases", "conversations", "tags"):
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "user_id" not in cols:
            op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))

    # 2. Backfill legacy owner only when unambiguous
    owner = _select_legacy_owner()
    if owner is not None:
        for table in ("documents", "knowledge_bases", "conversations", "tags"):
            op.execute(
                sa.text(f"UPDATE {table} SET user_id = :owner WHERE user_id IS NULL").bindparams(owner=owner)
            )

    # 3. Foreign keys to users (additive; skip if table has no user_id rows to violate)
    inspector = sa.inspect(conn)
    for table in ("documents", "knowledge_bases", "conversations", "tags"):
        fks = {fk["constrained_columns"][0] for fk in inspector.get_foreign_keys(table)}
        if "user_id" not in fks:
            op.create_foreign_key(
                f"fk_{table}_user", table, "users", ["user_id"], ["id"],
            )

    # 4. Composite indexes (user_id, id) and (user_id, kb_id)
    op.create_index("ix_documents_user_kb", "documents", ["user_id", "kb_id"])
    op.create_index("ix_documents_user_id", "documents", ["user_id", "id"])
    op.create_index("ix_kbs_user_id", "knowledge_bases", ["user_id", "id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id", "id"])
    op.create_index("ix_tags_user_id", "tags", ["user_id", "id"])


def downgrade() -> None:
    # Refuse to discard a populated ownership column
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tags_cols = {c["name"] for c in inspector.get_columns("tags")}
    if "user_id" in tags_cols:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM tags WHERE user_id IS NOT NULL")
        ).scalar()
        if count > 0:
            raise RuntimeError("refusing to drop populated tags.user_id column")

    op.drop_index("ix_tags_user_id", table_name="tags")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_kbs_user_id", table_name="knowledge_bases")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_index("ix_documents_user_kb", table_name="documents")

    for table in ("documents", "knowledge_bases", "conversations", "tags"):
        op.drop_constraint(f"fk_{table}_user", table, type_="foreignkey")
