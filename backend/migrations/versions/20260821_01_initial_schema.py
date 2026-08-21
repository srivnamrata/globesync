"""Initial application schema.

Revision ID: 20260821_01
Revises:
Create Date: 2026-08-21
"""

from alembic import op

from app.core.database import Base
from app.models import export_job, frame_metadata, generated_audio, lipsync_job, media, transcript, translation, voice_profile  # noqa: F401

revision = "20260821_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
