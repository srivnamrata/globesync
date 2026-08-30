"""Add nullable workspace scope to downstream pipeline tables.

Revision ID: 20260830_04
Revises: 20260829_03
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260830_04"
down_revision = "20260829_03"
branch_labels = None
depends_on = None


WORKSPACE_SCOPED_TABLES = (
    "media_files",
    "upload_sessions",
    "transcripts",
    "translations",
    "generated_audios",
    "lipsync_jobs",
    "export_jobs",
)


def upgrade() -> None:
    for table_name in WORKSPACE_SCOPED_TABLES:
        op.add_column(table_name, sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_workspace_id_workspaces",
            table_name,
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"], unique=False)

    op.execute(
        """
        UPDATE transcripts AS transcripts
        SET workspace_id = media.workspace_id
        FROM media_files AS media
        WHERE transcripts.workspace_id IS NULL
          AND transcripts.media_file_id = media.id
          AND media.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE translations AS translations
        SET workspace_id = transcripts.workspace_id
        FROM transcript_segments AS segments
        JOIN transcripts ON transcripts.id = segments.transcript_id
        WHERE translations.workspace_id IS NULL
          AND translations.transcript_segment_id = segments.id
          AND transcripts.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE generated_audios AS audio
        SET workspace_id = translations.workspace_id
        FROM translations
        WHERE audio.workspace_id IS NULL
          AND audio.translation_id = translations.id
          AND translations.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE lipsync_jobs AS jobs
        SET workspace_id = media.workspace_id
        FROM media_files AS media
        WHERE jobs.workspace_id IS NULL
          AND jobs.media_file_id = media.id
          AND media.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE lipsync_jobs AS jobs
        SET workspace_id = transcripts.workspace_id
        FROM transcripts
        WHERE jobs.workspace_id IS NULL
          AND jobs.transcript_id = transcripts.id
          AND transcripts.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE export_jobs AS jobs
        SET workspace_id = media.workspace_id
        FROM media_files AS media
        WHERE jobs.workspace_id IS NULL
          AND jobs.media_file_id = media.id
          AND media.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE export_jobs AS jobs
        SET workspace_id = transcripts.workspace_id
        FROM transcripts
        WHERE jobs.workspace_id IS NULL
          AND jobs.transcript_id = transcripts.id
          AND transcripts.workspace_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE upload_sessions AS sessions
        SET workspace_id = media.workspace_id
        FROM media_files AS media
        WHERE sessions.workspace_id IS NULL
          AND sessions.media_file_id = media.id
          AND media.workspace_id IS NOT NULL
        """
    )


def downgrade() -> None:
    for table_name in reversed(WORKSPACE_SCOPED_TABLES):
        op.drop_index(f"ix_{table_name}_workspace_id", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_workspace_id_workspaces", table_name, type_="foreignkey")
        op.drop_column(table_name, "workspace_id")
