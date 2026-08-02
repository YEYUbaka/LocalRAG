"""ingestion jobs shadow table

Revision ID: 20260802_0003
Revises: 20260802_0002
Create Date: 2026-08-03

Additive table for persistent ingestion job shadowing. Payload must never
contain file bytes, secrets, or absolute local paths.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260802_0003"
down_revision: Union[str, None] = "20260802_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("heartbeat", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ingestion_jobs_user"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], name="fk_ingestion_jobs_kb"),
    )
    op.create_index("ix_ingestion_jobs_status_lease", "ingestion_jobs", ["status", "lease_until"])
    op.create_index("ix_ingestion_jobs_user_kb", "ingestion_jobs", ["user_id", "kb_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_user_kb", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status_lease", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
