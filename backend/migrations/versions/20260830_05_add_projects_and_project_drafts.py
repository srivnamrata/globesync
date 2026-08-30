"""Add canonical projects and project_drafts tables.

Revision ID: 20260830_05
Revises: 20260830_04
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260830_05"
down_revision = "20260830_04"
branch_labels = None
depends_on = None


PROJECT_STATUS_VALUES = (
    "draft",
    "processing",
    "completed",
    "failed",
    "archived",
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("source_language", sa.String(length=16), nullable=True),
        sa.Column("target_language", sa.String(length=16), nullable=True),
        sa.Column("active_translation_language", sa.String(length=16), nullable=True),
        sa.Column("media_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_lipsync_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_export_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_rendered_video_gcs_path", sa.Text(), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            f"status IN {PROJECT_STATUS_VALUES}",
            name="ck_projects_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_projects_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_projects_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_projects_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["media_file_id"],
            ["media_files.id"],
            name="fk_projects_media_file_id_media_files",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_projects_transcript_id_transcripts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_lipsync_job_id"],
            ["lipsync_jobs.id"],
            name="fk_projects_current_lipsync_job_id_lipsync_jobs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["current_export_job_id"],
            ["export_jobs.id"],
            name="fk_projects_current_export_job_id_export_jobs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_projects_workspace_slug"),
    )

    op.create_table(
        "project_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("draft_schema_version", sa.Text(), nullable=False),
        sa.Column("draft_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("base_project_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_saved_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version >= 1", name="ck_project_drafts_version_gte_1"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_drafts_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_project_drafts_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_saved_by_user_id"],
            ["users.id"],
            name="fk_project_drafts_last_saved_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_drafts"),
        sa.UniqueConstraint("project_id", name="uq_project_drafts_project_id"),
    )

    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"], unique=False)
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"], unique=False)
    op.create_index("ix_projects_created_by_user_id", "projects", ["created_by_user_id"], unique=False)
    op.create_index("ix_projects_status", "projects", ["status"], unique=False)
    op.create_index(
        "ix_projects_workspace_updated_at",
        "projects",
        ["workspace_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_projects_workspace_owner_updated_at",
        "projects",
        ["workspace_id", "owner_user_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_projects_workspace_status_updated_at",
        "projects",
        ["workspace_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index("ix_project_drafts_project_id", "project_drafts", ["project_id"], unique=True)
    op.create_index("ix_project_drafts_workspace_id", "project_drafts", ["workspace_id"], unique=False)
    op.create_index(
        "ix_project_drafts_last_saved_by_user_id",
        "project_drafts",
        ["last_saved_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_drafts_workspace_updated_at",
        "project_drafts",
        ["workspace_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_drafts_workspace_updated_at", table_name="project_drafts")
    op.drop_index("ix_project_drafts_last_saved_by_user_id", table_name="project_drafts")
    op.drop_index("ix_project_drafts_workspace_id", table_name="project_drafts")
    op.drop_index("ix_project_drafts_project_id", table_name="project_drafts")
    op.drop_index("ix_projects_workspace_status_updated_at", table_name="projects")
    op.drop_index("ix_projects_workspace_owner_updated_at", table_name="projects")
    op.drop_index("ix_projects_workspace_updated_at", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_created_by_user_id", table_name="projects")
    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_index("ix_projects_workspace_id", table_name="projects")

    op.drop_table("project_drafts")
    op.drop_table("projects")
