"""Add transcript segment ordering index groundwork.

Revision ID: 20260901_08
Revises: 20260901_07
Create Date: 2026-09-01
"""

from alembic import op

revision = "20260901_08"
down_revision = "20260901_07"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_transcript_segments_transcript_id_sequence_order"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "transcript_segments",
        ["transcript_id", "sequence_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="transcript_segments")
