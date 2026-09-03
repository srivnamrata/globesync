"""Durable, workspace-scoped records for non-render background operations."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PipelineOperation(Base):
    """Tracks transcription and translation work independently of UI sessions.

    Render jobs already have dedicated durable tables. This record gives the
    same recovery properties to upstream operations without storing artifacts
    or duplicating the authoritative transcript/translation rows.
    """

    __tablename__ = "pipeline_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True, index=True)
    transcript_id = Column(UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="SET NULL"), nullable=True, index=True)

    operation_type = Column(String(32), nullable=False, index=True)  # transcription, translation
    target_language = Column(String(10), nullable=True)
    transcription_language = Column(String(10), nullable=True)
    max_speakers = Column(Integer, nullable=True)
    enable_noise_reduction = Column(Boolean, nullable=True)
    enable_loudness_norm = Column(Boolean, nullable=True)
    enable_vad = Column(Boolean, nullable=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    current_stage = Column(String(50), nullable=False, default="queued")
    last_successful_stage = Column(String(50), nullable=True)
    message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    request_id = Column(String(255), nullable=True, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    idempotency_key = Column(String(255), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
