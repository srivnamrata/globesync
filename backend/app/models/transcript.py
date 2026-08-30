import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Transcript(Base):
    """SQLAlchemy model representing a full transcription and diarization record."""
    __tablename__ = "transcripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    media_file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("media_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    detected_language = Column(String(10), default="en", nullable=False)
    confidence_score = Column(Numeric(5, 4), nullable=True)
    word_count = Column(Integer, default=0, nullable=False)
    speaker_count = Column(SmallInteger, default=1, nullable=False)
    full_text = Column(Text, nullable=True)
    raw_response = Column(JSONB, nullable=True)

    status = Column(String(50), default="queued", index=True)  # queued, in_progress, completed, failed
    error_message = Column(Text, nullable=True)
    processing_duration_seconds = Column(Numeric(8, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    segments = relationship(
        "TranscriptSegment",
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.sequence_order",
    )


class TranscriptSegment(Base):
    """SQLAlchemy model for individual speaker-attributed speech segments with word timings."""
    __tablename__ = "transcript_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    speaker_tag = Column(String(50), nullable=False, default="Speaker 1")  # e.g., "Speaker 1", "Speaker 2"
    assigned_voice_profile_id = Column(UUID(as_uuid=True), nullable=True)
    start_time_seconds = Column(Numeric(10, 3), nullable=False)
    end_time_seconds = Column(Numeric(10, 3), nullable=False)
    duration_seconds = Column(Numeric(10, 3), nullable=False)
    text = Column(Text, nullable=False)
    confidence = Column(Numeric(5, 4), nullable=True)

    # Word-level timing detail array:
    # [{"word": "Hello", "start": 0.12, "end": 0.45, "confidence": 0.98, "speaker": "Speaker 1"}, ...]
    words = Column(JSONB, nullable=False, default=list)
    sequence_order = Column(Integer, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    transcript = relationship("Transcript", back_populates="segments")
