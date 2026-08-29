import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, BigInteger
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Project(Base):
    """SQLAlchemy model for canonical project identity, ownership, and pipeline pointers."""
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    owner_user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)

    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False, index=True)
    source_language = Column(String(16), nullable=True)
    target_language = Column(String(16), nullable=True)
    active_translation_language = Column(String(16), nullable=True)

    media_file_id = Column(UUID(as_uuid=True), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True)
    transcript_id = Column(UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="SET NULL"), nullable=True)
    current_lipsync_job_id = Column(UUID(as_uuid=True), ForeignKey("lipsync_jobs.id", ondelete="SET NULL"), nullable=True)
    current_export_job_id = Column(UUID(as_uuid=True), ForeignKey("export_jobs.id", ondelete="SET NULL"), nullable=True)

    last_rendered_video_gcs_path = Column(Text, nullable=True)
    last_opened_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    draft = relationship("ProjectDraft", back_populates="project", uselist=False, cascade="all, delete-orphan")
    media_file = relationship("MediaFile", foreign_keys=[media_file_id])
    transcript = relationship("Transcript", foreign_keys=[transcript_id])
    current_lipsync_job = relationship("LipSyncJob", foreign_keys=[current_lipsync_job_id])
    current_export_job = relationship("ExportJob", foreign_keys=[current_export_job_id])


class ProjectDraft(Base):
    """SQLAlchemy model for latest persisted editor draft state with optimistic concurrency."""
    __tablename__ = "project_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version = Column(BigInteger, nullable=False)
    draft_schema_version = Column(Text, nullable=False)
    draft_payload = Column(JSONB, nullable=False)
    base_project_updated_at = Column(DateTime(timezone=True), nullable=True)
    last_saved_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    project = relationship("Project", back_populates="draft")
