"""Add workflow correlation and provenance foundation columns.

Revision ID: 20260901_07
Revises: 20260830_06
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_07"
down_revision = "20260830_06"
branch_labels = None
depends_on = None

REQUEST_TRACKED_TABLES = (
    "translations",
    "generated_audios",
    "lipsync_jobs",
    "export_jobs",
)

IDEMPOTENCY_TRACKED_TABLES = (
    "translations",
    "generated_audios",
    "lipsync_jobs",
    "export_jobs",
)


def upgrade() -> None:
    op.add_column("transcript_segments", sa.Column("origin_type", sa.String(length=50), nullable=True))
    op.add_column("transcript_segments", sa.Column("source_action", sa.String(length=100), nullable=True))
    op.add_column("translations", sa.Column("source_action", sa.String(length=100), nullable=True))

    for table_name in REQUEST_TRACKED_TABLES:
        op.add_column(table_name, sa.Column("request_id", sa.String(length=255), nullable=True))
        op.add_column(table_name, sa.Column("task_id", sa.String(length=255), nullable=True))
        op.create_index(f"ix_{table_name}_request_id", table_name, ["request_id"], unique=False)
        op.create_index(f"ix_{table_name}_task_id", table_name, ["task_id"], unique=False)

    for table_name in IDEMPOTENCY_TRACKED_TABLES:
        op.add_column(table_name, sa.Column("idempotency_key", sa.String(length=255), nullable=True))
        op.create_index(f"ix_{table_name}_idempotency_key", table_name, ["idempotency_key"], unique=False)


def downgrade() -> None:
    for table_name in reversed(IDEMPOTENCY_TRACKED_TABLES):
        op.drop_index(f"ix_{table_name}_idempotency_key", table_name=table_name)
        op.drop_column(table_name, "idempotency_key")

    for table_name in reversed(REQUEST_TRACKED_TABLES):
        op.drop_index(f"ix_{table_name}_task_id", table_name=table_name)
        op.drop_index(f"ix_{table_name}_request_id", table_name=table_name)
        op.drop_column(table_name, "task_id")
        op.drop_column(table_name, "request_id")

    op.drop_column("translations", "source_action")
    op.drop_column("transcript_segments", "source_action")
    op.drop_column("transcript_segments", "origin_type")
