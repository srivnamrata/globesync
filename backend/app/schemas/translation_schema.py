from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from app.utils.language_configs import get_supported_language_codes, is_supported_language_code, normalize_language_code


SUPPORTED_LANGUAGE_CODES = get_supported_language_codes()
SUPPORTED_LANGUAGE_CODES_MESSAGE = ", ".join(SUPPORTED_LANGUAGE_CODES)


class TranslateProjectRequest(BaseModel):
    transcript_id: UUID
    target_language: str = Field(
        ...,
        description="Target ISO 639-1 language code",
        json_schema_extra={"example": "es"},
    )
    source_language: str = Field(
        "en",
        description="Source language code",
        json_schema_extra={"example": "en"},
    )
    tone: str = Field(
        "natural",
        description="Tone (natural, formal, casual, emotive)",
        json_schema_extra={"example": "natural"},
    )

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_supported_language(cls, value: str) -> str:
        normalized = normalize_language_code(value)
        if not is_supported_language_code(value):
            raise ValueError(f"Unsupported language code '{value}'. Supported codes: {SUPPORTED_LANGUAGE_CODES_MESSAGE}")
        return normalized


class TranslateSegmentRequest(BaseModel):
    segment_id: UUID
    source_text: str = Field(..., json_schema_extra={"example": "Welcome to our global conference."})
    original_duration_ms: int = Field(..., gt=0, json_schema_extra={"example": 3500})
    source_language: str = Field("en", json_schema_extra={"example": "en"})
    target_language: str = Field(..., json_schema_extra={"example": "es"})
    speaker_tag: str = Field("Speaker 1", json_schema_extra={"example": "Speaker 1"})
    previous_context: Optional[str] = None
    next_context: Optional[str] = None

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_supported_language(cls, value: str) -> str:
        normalized = normalize_language_code(value)
        if not is_supported_language_code(value):
            raise ValueError(f"Unsupported language code '{value}'. Supported codes: {SUPPORTED_LANGUAGE_CODES_MESSAGE}")
        return normalized


class UpdateTranslationRequest(BaseModel):
    translated_text: str = Field(
        ...,
        json_schema_extra={"example": "Bienvenidos a nuestra conferencia global."},
    )


class SupportedLanguageResponse(BaseModel):
    code: str
    name: str
    native_name: str


class SupportedLanguagesResponse(BaseModel):
    languages: List[SupportedLanguageResponse]


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
    generated_audio_status: Optional[str] = None
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
