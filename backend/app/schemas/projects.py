from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from app.utils.language_configs import get_supported_language_codes, is_supported_language_code, normalize_language_code


SUPPORTED_LANGUAGE_CODES = get_supported_language_codes()
SUPPORTED_LANGUAGE_CODES_MESSAGE = ", ".join(SUPPORTED_LANGUAGE_CODES)
PROJECT_STATUS_VALUES = ("draft", "processing", "completed", "failed", "archived")
ProjectStatus = Literal["draft", "processing", "completed", "failed", "archived"]


class ProjectListQueryParams(BaseModel):
    status: Optional[ProjectStatus] = Field(None, json_schema_extra={"example": "draft"})
    limit: int = Field(20, ge=1, le=100, json_schema_extra={"example": 20})
    cursor: Optional[str] = Field(None, json_schema_extra={"example": None})
    include_archived: bool = Field(False, json_schema_extra={"example": False})


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, json_schema_extra={"example": "Hindi Product Launch"})
    source_language: str = Field(..., json_schema_extra={"example": "en"})
    target_language: str = Field(..., json_schema_extra={"example": "hi"})

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_supported_language(cls, value: str) -> str:
        normalized = normalize_language_code(value)
        if not is_supported_language_code(value):
            raise ValueError(f"Unsupported language code '{value}'. Supported codes: {SUPPORTED_LANGUAGE_CODES_MESSAGE}")
        return normalized


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255, json_schema_extra={"example": "Hindi Product Launch v2"})
    status: Optional[ProjectStatus] = Field(None, json_schema_extra={"example": "processing"})
    source_language: Optional[str] = Field(None, json_schema_extra={"example": "en"})
    target_language: Optional[str] = Field(None, json_schema_extra={"example": "hi"})
    active_translation_language: Optional[str] = Field(None, json_schema_extra={"example": "hi"})
    media_file_id: Optional[UUID] = Field(None, json_schema_extra={"example": "0f7df8e2-a8d1-4c2b-a7fc-4a8011a6e5c9"})
    transcript_id: Optional[UUID] = Field(None, json_schema_extra={"example": "25cda2d1-7726-4b65-a410-d204c80910ea"})
    current_lipsync_job_id: Optional[UUID] = Field(None, json_schema_extra={"example": "30c4e7f5-f529-44a4-b7a7-8d4ce1262530"})
    current_export_job_id: Optional[UUID] = Field(None, json_schema_extra={"example": "7374f6a8-73fc-4987-ab22-1d8022dbf769"})
    last_rendered_video_gcs_path: Optional[str] = Field(None, max_length=2048, json_schema_extra={"example": "gs://project-794c406e-c0ab-4a50-8e9-media-exports/master_dubbed/video.mp4"})

    @field_validator("source_language", "target_language", "active_translation_language")
    @classmethod
    def validate_supported_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = normalize_language_code(value)
        if not is_supported_language_code(value):
            raise ValueError(f"Unsupported language code '{value}'. Supported codes: {SUPPORTED_LANGUAGE_CODES_MESSAGE}")
        return normalized


class ProjectDraftPutRequest(BaseModel):
    version: int = Field(..., ge=1, json_schema_extra={"example": 7})
    draft_schema_version: str = Field(..., min_length=1, json_schema_extra={"example": "heygenx/v1"})
    base_project_updated_at: Optional[datetime] = Field(None, json_schema_extra={"example": "2026-08-29T09:42:10Z"})
    draft_payload: Dict[str, Any] = Field(...)
    checkpoint_reason: Optional[str] = Field(None, max_length=50, json_schema_extra={"example": "manual_save"})


class ProjectSummaryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    name: str
    status: ProjectStatus
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    active_translation_language: Optional[str] = None
    media_file_id: Optional[UUID] = None
    media_filename: Optional[str] = None
    media_duration_seconds: Optional[float] = None
    pipeline_stage: Optional[str] = None
    pipeline_status: Optional[str] = None
    pipeline_progress_percent: Optional[int] = None
    pipeline_error_message: Optional[str] = None
    transcript_id: Optional[UUID] = None
    latest_draft_version: int = Field(0)
    last_rendered_video_gcs_path: Optional[str] = None
    last_opened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: List[ProjectSummaryResponse] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class ProjectDetailResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    owner_user_id: UUID
    created_by_user_id: UUID
    name: str
    slug: Optional[str] = None
    status: ProjectStatus
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    active_translation_language: Optional[str] = None
    media_file_id: Optional[UUID] = None
    transcript_id: Optional[UUID] = None
    current_lipsync_job_id: Optional[UUID] = None
    current_export_job_id: Optional[UUID] = None
    last_rendered_video_gcs_path: Optional[str] = None
    latest_draft_version: int = Field(0)
    archived_at: Optional[datetime] = None
    last_opened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProjectDraftResponse(BaseModel):
    project_id: UUID
    workspace_id: UUID
    version: int
    draft_schema_version: str
    base_project_updated_at: Optional[datetime] = None
    last_saved_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    draft_payload: Dict[str, Any] = Field(default_factory=dict)


class ProjectDraftPutResponse(BaseModel):
    project_id: UUID
    workspace_id: UUID
    version: int
    draft_schema_version: str
    base_project_updated_at: Optional[datetime] = None
    last_saved_by_user_id: UUID
    updated_at: datetime


class ProjectVersionSummaryResponse(BaseModel):
    version: int
    draft_schema_version: str
    created_by_user_id: UUID
    created_at: datetime


class ProjectVersionListResponse(BaseModel):
    items: List[ProjectVersionSummaryResponse] = Field(default_factory=list)


class ProjectVersionResponse(ProjectVersionSummaryResponse):
    draft_payload: Dict[str, Any]


class ProjectArchiveResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    status: ProjectStatus
    archived_at: Optional[datetime] = None
    updated_at: datetime


class DraftConflictErrorDetail(BaseModel):
    code: Literal["DRAFT_VERSION_CONFLICT"] = "DRAFT_VERSION_CONFLICT"
    message: str = Field(
        default="The draft has been updated by another session. Refresh before saving again.",
    )
    project_id: UUID
    client_version: int
    server_version: int
    server_updated_at: datetime
    last_saved_by_user_id: UUID


class DraftConflictErrorResponse(BaseModel):
    error: DraftConflictErrorDetail
