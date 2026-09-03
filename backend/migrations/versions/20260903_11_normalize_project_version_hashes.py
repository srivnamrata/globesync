"""Normalize project version hashes to the runtime canonical JSON algorithm.

Revision ID: 20260903_11
Revises: 20260903_10
Create Date: 2026-09-03
"""

import hashlib
import json

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260903_11"
down_revision = "20260903_10"
branch_labels = None
depends_on = None


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade() -> None:
    if context.is_offline_mode():
        return

    project_versions = sa.table(
        "project_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("draft_payload", postgresql.JSONB),
        sa.column("payload_hash", sa.String(length=64)),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(project_versions.c.id, project_versions.c.draft_payload)
    ).mappings()
    for row in rows:
        connection.execute(
            project_versions.update()
            .where(project_versions.c.id == row["id"])
            .values(payload_hash=_hash_payload(row["draft_payload"]))
        )


def downgrade() -> None:
    pass
