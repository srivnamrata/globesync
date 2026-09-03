"""Track lip-sync render mode so finished outputs are auditable and independently downloadable.

Revision ID: 20260903_12
Revises: 20260903_11
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_12"
down_revision = "20260903_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lipsync_jobs",
        sa.Column(
            "render_mode",
            sa.String(length=32),
            nullable=False,
            server_default="dub_and_lipsync",
        ),
    )
    op.create_index("ix_lipsync_jobs_render_mode", "lipsync_jobs", ["render_mode"])
    op.alter_column("lipsync_jobs", "render_mode", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_lipsync_jobs_render_mode", table_name="lipsync_jobs")
    op.drop_column("lipsync_jobs", "render_mode")
