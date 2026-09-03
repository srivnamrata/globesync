"""Add durable upstream pipeline operation tracking.

Revision ID: 20260903_15
Revises: 20260903_14
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260903_15"
down_revision = "20260903_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("media_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("target_language", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("last_successful_stage", sa.String(length=50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_pipeline_operations_project_id_projects", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_pipeline_operations_workspace_id_workspaces", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_files.id"], name="fk_pipeline_operations_media_file_id_media_files", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], name="fk_pipeline_operations_transcript_id_transcripts", ondelete="SET NULL"),
    )
    for column in ("project_id", "workspace_id", "media_file_id", "transcript_id", "operation_type", "status", "request_id", "task_id", "idempotency_key"):
        op.create_index(f"ix_pipeline_operations_{column}", "pipeline_operations", [column], unique=False)

    op.add_column("projects", sa.Column("current_pipeline_operation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projects_current_pipeline_operation_id_pipeline_operations",
        "projects",
        "pipeline_operations",
        ["current_pipeline_operation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_current_pipeline_operation_id_pipeline_operations", "projects", type_="foreignkey")
    op.drop_column("projects", "current_pipeline_operation_id")
    for column in ("idempotency_key", "task_id", "request_id", "status", "operation_type", "transcript_id", "media_file_id", "workspace_id", "project_id"):
        op.drop_index(f"ix_pipeline_operations_{column}", table_name="pipeline_operations")
    op.drop_table("pipeline_operations")
