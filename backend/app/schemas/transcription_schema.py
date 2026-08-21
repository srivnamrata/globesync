from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class WordDetail(BaseModel):
    text: str = Field(..., example="Hello")
    start: float = Field(..., example=2.0)
    end: float = Field(..., example=2.3)
    confidence: float = Field(..., ge=0.0, le=1.0, example=0.98)
    speaker: Optional[str] = Field(None, example="Speaker 1")


class SegmentResponse(BaseModel):
    id: Optional[UUID] = None
    start_time: float = Field(..., example=2.0)
    end_time: float = Field(..., example=8.5)
    duration: float = Field(..., example=6.5)
    speaker: str = Field(..., example="Speaker 1")
    text: str = Field(..., example="Hello, this is a test")
    confidence: Optional[float] = Field(None, example=0.97)
    words: List[WordDetail] = Field(default_factory=list)
    sequence_order: int = Field(0, example=0)


class TranscriptResponse(BaseModel):
    transcript_id: UUID
    media_id: UUID
    status: str = Field(..., example="completed")
    language: str = Field(..., example="en")
    confidence_score: Optional[float] = Field(None, example=0.965)
    word_count: int = Field(0, example=450)
    speaker_count: int = Field(1, example=2)
    full_text: Optional[str] = None
    segments: List[SegmentResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class StartTranscriptionRequest(BaseModel):
    media_id: UUID
    language: Optional[str] = Field(None, example="en", description="ISO 639-1 language code or None for auto-detect")
    max_speakers: Optional[int] = Field(None, ge=1, le=10, example=3, description="Estimated number of speakers for diarization")
    enable_noise_reduction: bool = Field(True, description="Apply spectral subtraction and high-pass filtering")
    enable_loudness_norm: bool = Field(True, description="Normalize audio to -20 LUFS")
    enable_vad: bool = Field(True, description="Voice Activity Detection and silence trimming")


class TranscriptionJobResponse(BaseModel):
    job_id: str
    transcript_id: UUID
    media_id: UUID
    status: str = Field(default="queued")
    message: str = Field(default="Audio extraction and transcription task dispatched.")
