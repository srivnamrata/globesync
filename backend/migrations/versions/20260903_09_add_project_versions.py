"""Add immutable project draft versions.

Revision ID: 20260903_09
Revises: 20260901_08
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260903_09"
down_revision = "20260901_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_schema_version", sa.String(length=64), nullable=False),
        sa.Column("draft_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_versions_project_version"),
    )
    op.create_index("ix_project_versions_project_id", "project_versions", ["project_id"])
    op.create_index("ix_project_versions_workspace_id", "project_versions", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_project_versions_workspace_id", table_name="project_versions")
    op.drop_index("ix_project_versions_project_id", table_name="project_versions")
    op.drop_table("project_versions")
