"""Persist lip-sync pipeline checkpoints for recovery-aware UI progress.

Revision ID: 20260903_14
Revises: 20260903_13
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_14"
down_revision = "20260903_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lipsync_jobs",
        sa.Column("current_stage", sa.String(length=50), nullable=False, server_default="queued"),
    )
    op.add_column(
        "lipsync_jobs",
        sa.Column("last_successful_stage", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lipsync_jobs", "last_successful_stage")
    op.drop_column("lipsync_jobs", "current_stage")
