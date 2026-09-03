"""Add metadata for bounded project version snapshots.

Revision ID: 20260903_10
Revises: 20260903_09
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = "20260903_10"
down_revision = "20260903_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_versions",
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "project_versions",
        sa.Column("checkpoint_reason", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_project_versions_payload_hash", "project_versions", ["payload_hash"])
    op.execute("UPDATE project_versions SET checkpoint_reason = 'legacy' WHERE checkpoint_reason IS NULL")
    op.execute("UPDATE project_versions SET payload_hash = md5(CAST(draft_payload AS text)) WHERE payload_hash IS NULL")
    op.alter_column("project_versions", "payload_hash", nullable=False)
    op.alter_column("project_versions", "checkpoint_reason", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_project_versions_payload_hash", table_name="project_versions")
    op.drop_column("project_versions", "checkpoint_reason")
    op.drop_column("project_versions", "payload_hash")
