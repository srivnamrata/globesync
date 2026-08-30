"""Backfill canonical project scope on pipeline tables.

Revision ID: 20260830_06
Revises: 20260830_05
Create Date: 2026-08-30
"""

from alembic import op

revision = "20260830_06"
down_revision = "20260830_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE media_files AS media
        SET project_id = COALESCE(media.project_id, projects.id),
            workspace_id = COALESCE(media.workspace_id, projects.workspace_id),
            user_id = COALESCE(media.user_id, projects.owner_user_id)
        FROM projects
        WHERE (
            media.project_id = projects.id
            OR projects.media_file_id = media.id
        )
          AND (
            media.project_id IS NULL
            OR media.workspace_id IS NULL
            OR media.user_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE upload_sessions AS sessions
        SET workspace_id = COALESCE(sessions.workspace_id, media.workspace_id),
            user_id = COALESCE(sessions.user_id, media.user_id)
        FROM media_files AS media
        WHERE sessions.media_file_id = media.id
          AND media.workspace_id IS NOT NULL
          AND (
            sessions.workspace_id IS NULL
            OR sessions.user_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE transcripts AS transcripts
        SET project_id = COALESCE(transcripts.project_id, projects.id),
            workspace_id = COALESCE(transcripts.workspace_id, projects.workspace_id)
        FROM projects
        WHERE (
            transcripts.project_id = projects.id
            OR projects.transcript_id = transcripts.id
        )
          AND (
            transcripts.project_id IS NULL
            OR transcripts.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE transcripts AS transcripts
        SET project_id = COALESCE(transcripts.project_id, media.project_id),
            workspace_id = COALESCE(transcripts.workspace_id, media.workspace_id)
        FROM media_files AS media
        WHERE transcripts.media_file_id = media.id
          AND (
            media.project_id IS NOT NULL
            OR media.workspace_id IS NOT NULL
          )
          AND (
            transcripts.project_id IS NULL
            OR transcripts.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE translations AS translations
        SET project_id = COALESCE(translations.project_id, transcripts.project_id),
            workspace_id = COALESCE(translations.workspace_id, transcripts.workspace_id)
        FROM transcript_segments AS segments
        JOIN transcripts ON transcripts.id = segments.transcript_id
        WHERE translations.transcript_segment_id = segments.id
          AND (
            transcripts.project_id IS NOT NULL
            OR transcripts.workspace_id IS NOT NULL
          )
          AND (
            translations.project_id IS NULL
            OR translations.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE generated_audios AS audio
        SET project_id = COALESCE(audio.project_id, translations.project_id),
            workspace_id = COALESCE(audio.workspace_id, translations.workspace_id)
        FROM translations
        WHERE audio.translation_id = translations.id
          AND (
            translations.project_id IS NOT NULL
            OR translations.workspace_id IS NOT NULL
          )
          AND (
            audio.project_id IS NULL
            OR audio.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE lipsync_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, projects.id),
            workspace_id = COALESCE(jobs.workspace_id, projects.workspace_id)
        FROM projects
        WHERE (
            jobs.project_id = projects.id
            OR projects.current_lipsync_job_id = jobs.id
        )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE lipsync_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, media.project_id),
            workspace_id = COALESCE(jobs.workspace_id, media.workspace_id)
        FROM media_files AS media
        WHERE jobs.media_file_id = media.id
          AND (
            media.project_id IS NOT NULL
            OR media.workspace_id IS NOT NULL
          )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE lipsync_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, transcripts.project_id),
            workspace_id = COALESCE(jobs.workspace_id, transcripts.workspace_id)
        FROM transcripts
        WHERE jobs.transcript_id = transcripts.id
          AND (
            transcripts.project_id IS NOT NULL
            OR transcripts.workspace_id IS NOT NULL
          )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE export_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, projects.id),
            workspace_id = COALESCE(jobs.workspace_id, projects.workspace_id)
        FROM projects
        WHERE (
            jobs.project_id = projects.id
            OR projects.current_export_job_id = jobs.id
        )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE export_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, media.project_id),
            workspace_id = COALESCE(jobs.workspace_id, media.workspace_id)
        FROM media_files AS media
        WHERE jobs.media_file_id = media.id
          AND (
            media.project_id IS NOT NULL
            OR media.workspace_id IS NOT NULL
          )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE export_jobs AS jobs
        SET project_id = COALESCE(jobs.project_id, transcripts.project_id),
            workspace_id = COALESCE(jobs.workspace_id, transcripts.workspace_id)
        FROM transcripts
        WHERE jobs.transcript_id = transcripts.id
          AND (
            transcripts.project_id IS NOT NULL
            OR transcripts.workspace_id IS NOT NULL
          )
          AND (
            jobs.project_id IS NULL
            OR jobs.workspace_id IS NULL
          )
        """
    )


def downgrade() -> None:
    pass
