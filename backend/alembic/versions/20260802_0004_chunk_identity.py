"""tenant-scoped document hashes and stable chunk identity

Revision ID: 20260802_0004
Revises: 20260802_0003
Create Date: 2026-08-23

The new identity columns are additive. ``document_key`` remains nullable so
legacy rows can be read without inventing an identity during schema upgrade.
New ingestion always populates it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260802_0004"
down_revision: Union[str, None] = "20260802_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _md5_unique_constraint_names() -> list[str]:
    inspector = sa.inspect(op.get_bind())
    return [
        constraint["name"]
        for constraint in inspector.get_unique_constraints("documents")
        if constraint.get("name")
        and constraint.get("column_names") == ["md5_hash"]
    ]


def upgrade() -> None:
    op.add_column("documents", sa.Column("document_key", sa.String(64), nullable=True))
    op.add_column(
        "documents",
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "documents",
        sa.Column("chunker_version", sa.String(32), nullable=False, server_default="1"),
    )

    for constraint_name in _md5_unique_constraint_names():
        op.drop_constraint(constraint_name, "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_scope_md5",
        "documents",
        ["user_id", "kb_id", "md5_hash"],
    )


def downgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT md5_hash FROM documents "
            "GROUP BY md5_hash HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot restore global documents.md5_hash uniqueness while duplicate hashes exist"
        )

    op.drop_constraint("uq_documents_scope_md5", "documents", type_="unique")
    op.create_unique_constraint("uq_documents_md5_hash", "documents", ["md5_hash"])
    op.drop_column("documents", "chunker_version")
    op.drop_column("documents", "document_version")
    op.drop_column("documents", "document_key")
