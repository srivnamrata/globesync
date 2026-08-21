from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TranslateProjectRequest(BaseModel):
    transcript_id: UUID
    target_language: str = Field(..., example="es", description="Target ISO 639-1 language code")
    source_language: str = Field("en", example="en", description="Source language code")
    tone: str = Field("natural", example="natural", description="Tone (natural, formal, casual, emotive)")


class TranslateSegmentRequest(BaseModel):
    segment_id: UUID
    source_text: str = Field(..., example="Welcome to our global conference.")
    original_duration_ms: int = Field(..., gt=0, example=3500)
    source_language: str = Field("en", example="en")
    target_language: str = Field(..., example="es")
    speaker_tag: str = Field("Speaker 1", example="Speaker 1")
    previous_context: Optional[str] = None
    next_context: Optional[str] = None


class UpdateTranslationRequest(BaseModel):
    translated_text: str = Field(..., example="Bienvenidos a nuestra conferencia global.")


class TranslationItemResponse(BaseModel):
    translation_id: UUID
    segment_id: UUID
    sequence_order: int
    speaker_tag: str
    start_time_seconds: float
    end_time_seconds: float
    source_text: str
    translated_text: str
    original_duration_ms: int
    estimated_duration_ms: int
    duration_ratio: float
    duration_status: str
    iterations_count: int
    confidence_score: float
    is_cached: bool
    is_user_edited: bool
    created_at: datetime


class ProjectTranslationResponse(BaseModel):
    transcript_id: UUID
    target_language: str
    total_segments: int
    average_duration_ratio: float
    overall_confidence: float
    translations: List[TranslationItemResponse]


class TranslationJobResponse(BaseModel):
    job_id: str
    transcript_id: UUID
    target_language: str
    status: str = Field(default="queued")
    message: str = Field(default="Translation job dispatched to Celery worker queue.")
