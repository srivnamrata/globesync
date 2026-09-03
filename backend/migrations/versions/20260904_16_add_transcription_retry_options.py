"""Persist transcription inputs for safe retries.

Revision ID: 20260904_16
Revises: 20260903_15
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_16"
down_revision = "20260903_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_operations", sa.Column("transcription_language", sa.String(length=10), nullable=True))
    op.add_column("pipeline_operations", sa.Column("max_speakers", sa.Integer(), nullable=True))
    op.add_column("pipeline_operations", sa.Column("enable_noise_reduction", sa.Boolean(), nullable=True))
    op.add_column("pipeline_operations", sa.Column("enable_loudness_norm", sa.Boolean(), nullable=True))
    op.add_column("pipeline_operations", sa.Column("enable_vad", sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column in ("enable_vad", "enable_loudness_norm", "enable_noise_reduction", "max_speakers", "transcription_language"):
        op.drop_column("pipeline_operations", column)