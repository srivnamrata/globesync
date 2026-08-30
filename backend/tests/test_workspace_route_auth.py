import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
import sys
import types
import uuid

import pytest
from fastapi import HTTPException
from pydantic import BaseModel


class _Field:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return (self.name, "==", other)

    def in_(self, values):
        return (self.name, "in", tuple(values))

    def is_(self, value):
        return (self.name, "is", value)

    def desc(self):
        return (self.name, "desc")


class _Select:
    def __init__(self, *entities):
        self.entities = entities

    def where(self, *conditions):
        self.conditions = conditions
        return self

    def options(self, *options):
        self.options_applied = options
        return self

    def order_by(self, *ordering):
        self.ordering = ordering
        return self

    def limit(self, value):
        self.limit_value = value
        return self


sqlalchemy_module = types.ModuleType("sqlalchemy")
sqlalchemy_module.select = lambda *args, **kwargs: _Select(*args)
sqlalchemy_module.or_ = lambda *args: ("or", args)
sys.modules["sqlalchemy"] = sqlalchemy_module

sqlalchemy_ext_module = types.ModuleType("sqlalchemy.ext")
sqlalchemy_ext_asyncio_module = types.ModuleType("sqlalchemy.ext.asyncio")
sqlalchemy_ext_asyncio_module.AsyncSession = object
sys.modules["sqlalchemy.ext"] = sqlalchemy_ext_module
sys.modules["sqlalchemy.ext.asyncio"] = sqlalchemy_ext_asyncio_module

sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
sqlalchemy_orm_module.selectinload = lambda value: ("selectinload", value)
sys.modules["sqlalchemy.orm"] = sqlalchemy_orm_module

aiofiles_module = types.ModuleType("aiofiles")


class _AsyncFile:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def write(self, data):
        return None


aiofiles_module.open = lambda *args, **kwargs: _AsyncFile()
sys.modules.setdefault("aiofiles", aiofiles_module)

redis_module = types.ModuleType("redis")
redis_module.Redis = SimpleNamespace(from_url=lambda *args, **kwargs: SimpleNamespace(publish=lambda *a, **k: None))
sys.modules.setdefault("redis", redis_module)

redis_asyncio_module = types.ModuleType("redis.asyncio")
sys.modules.setdefault("redis.asyncio", redis_asyncio_module)

multipart_module = types.ModuleType("multipart")
multipart_module.__version__ = "0.0-test"
sys.modules["multipart"] = multipart_module

multipart_submodule = types.ModuleType("multipart.multipart")
multipart_submodule.parse_options_header = lambda value: (b"form-data", {})
sys.modules["multipart.multipart"] = multipart_submodule

app_core_config_module = types.ModuleType("app.core.config")
app_core_config_module.settings = SimpleNamespace(
    TEMP_UPLOAD_DIR="/tmp",
    MAX_FILE_SIZE_BYTES=1024,
    MULTIPART_CHUNK_SIZE_BYTES=8,
    STORAGE_PROVIDER="gcs",
    GCS_BUCKET_NAME="bucket",
    TRANSLATION_SYNC_FALLBACK=False,
    ENABLE_BACKGROUND_PIPELINES=True,
)
sys.modules.setdefault("app.core.config", app_core_config_module)

app_core_database_module = types.ModuleType("app.core.database")
app_core_database_module.get_db = lambda: None
sys.modules.setdefault("app.core.database", app_core_database_module)


@dataclass
class AuthenticatedRequestContext:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str = "editor"


async def _noop_auth(*args, **kwargs):
    return None


async def _noop_project(*args, **kwargs):
    return SimpleNamespace(id=kwargs.get("project_id"))


app_core_auth_module = types.ModuleType("app.core.auth")
app_core_auth_module.AuthenticatedRequestContext = AuthenticatedRequestContext
app_core_auth_module.ensure_workspace_resource_access = _noop_auth
app_core_auth_module.get_scoped_project = _noop_project
app_core_auth_module.get_request_context = lambda: None
app_core_auth_module.require_workspace_write_context = lambda: None
sys.modules.setdefault("app.core.auth", app_core_auth_module)


class _ModelBase:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MediaFile(_ModelBase):
    id = _Field("id")
    project_id = _Field("project_id")
    workspace_id = _Field("workspace_id")
    user_id = _Field("user_id")


class UploadChunk(_ModelBase):
    session_id = _Field("session_id")
    chunk_index = _Field("chunk_index")


class UploadSession(_ModelBase):
    id = _Field("id")
    chunks = _Field("chunks")
    workspace_id = _Field("workspace_id")
    user_id = _Field("user_id")
    media_file_id = _Field("media_file_id")
    status = _Field("status")
    expires_at = _Field("expires_at")
    total_chunks = _Field("total_chunks")
    filesize_bytes = _Field("filesize_bytes")
    bytes_received = _Field("bytes_received")
    filename = _Field("filename")


class TranscriptSegment(_ModelBase):
    transcript_id = _Field("transcript_id")
    sequence_order = _Field("sequence_order")


class Transcript(_ModelBase):
    id = _Field("id")
    media_file_id = _Field("media_file_id")
    project_id = _Field("project_id")
    workspace_id = _Field("workspace_id")
    detected_language = _Field("detected_language")
    segments = _Field("segments")


class Translation(_ModelBase):
    id = _Field("id")
    transcript_segment_id = _Field("transcript_segment_id")
    target_language = _Field("target_language")
    project_id = _Field("project_id")
    workspace_id = _Field("workspace_id")


class GeneratedAudio(_ModelBase):
    id = _Field("id")


class LipSyncJob(_ModelBase):
    id = _Field("id")
    segments_metadata = _Field("segments_metadata")
    project_id = _Field("project_id")
    workspace_id = _Field("workspace_id")


class FrameMetadata(_ModelBase):
    pass


class ExportJob(_ModelBase):
    id = _Field("id")
    project_id = _Field("project_id")
    workspace_id = _Field("workspace_id")


class Project(_ModelBase):
    id = _Field("id")


app_models_media_module = types.ModuleType("app.models.media")
app_models_media_module.MediaFile = MediaFile
app_models_media_module.UploadChunk = UploadChunk
app_models_media_module.UploadSession = UploadSession
sys.modules.setdefault("app.models.media", app_models_media_module)

app_models_transcript_module = types.ModuleType("app.models.transcript")
app_models_transcript_module.Transcript = Transcript
app_models_transcript_module.TranscriptSegment = TranscriptSegment
sys.modules.setdefault("app.models.transcript", app_models_transcript_module)

app_models_translation_module = types.ModuleType("app.models.translation")
app_models_translation_module.Translation = Translation
sys.modules.setdefault("app.models.translation", app_models_translation_module)

app_models_generated_audio_module = types.ModuleType("app.models.generated_audio")
app_models_generated_audio_module.GeneratedAudio = GeneratedAudio
sys.modules.setdefault("app.models.generated_audio", app_models_generated_audio_module)

app_models_lipsync_job_module = types.ModuleType("app.models.lipsync_job")
app_models_lipsync_job_module.LipSyncJob = LipSyncJob
sys.modules.setdefault("app.models.lipsync_job", app_models_lipsync_job_module)

app_models_frame_metadata_module = types.ModuleType("app.models.frame_metadata")
app_models_frame_metadata_module.FrameMetadata = FrameMetadata
sys.modules.setdefault("app.models.frame_metadata", app_models_frame_metadata_module)

app_models_export_job_module = types.ModuleType("app.models.export_job")
app_models_export_job_module.ExportJob = ExportJob
sys.modules.setdefault("app.models.export_job", app_models_export_job_module)

app_models_project_module = types.ModuleType("app.models.project")
app_models_project_module.Project = Project
sys.modules.setdefault("app.models.project", app_models_project_module)

app_schemas_media_module = types.ModuleType("app.schemas.media_schema")
for name in [
    "ChunkUploadResponse",
    "CompleteUploadRequest",
    "InitResumableUploadRequest",
    "InitResumableUploadResponse",
    "InitSignedUploadRequest",
    "InitSignedUploadResponse",
    "MediaFileResponse",
    "UploadStatusResponse",
]:
    setattr(app_schemas_media_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.media_schema", app_schemas_media_module)

app_schemas_transcription_module = types.ModuleType("app.schemas.transcription_schema")
for name in [
    "SegmentResponse",
    "StartTranscriptionRequest",
    "TranscriptionJobResponse",
    "TranscriptResponse",
    "WordDetail",
]:
    setattr(app_schemas_transcription_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.transcription_schema", app_schemas_transcription_module)

app_schemas_translation_module = types.ModuleType("app.schemas.translation_schema")
for name in [
    "ProjectTranslationResponse",
    "SupportedLanguagesResponse",
    "SupportedLanguageResponse",
    "TranslateProjectRequest",
    "TranslateSegmentRequest",
    "TranslationItemResponse",
    "TranslationJobResponse",
    "UpdateTranslationRequest",
]:
    setattr(app_schemas_translation_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.translation_schema", app_schemas_translation_module)

app_schemas_tts_module = types.ModuleType("app.schemas.tts_schema")
for name in [
    "GeneratedAudioResponse",
    "MasterDubbedAudioResponse",
    "SynthesizeProjectTTSRequest",
    "SynthesizeSegmentTTSRequest",
    "TTSJobResponse",
]:
    setattr(app_schemas_tts_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.tts_schema", app_schemas_tts_module)

app_schemas_lipsync_module = types.ModuleType("app.schemas.lipsync_schema")
for name in [
    "FrameMetadataResponse",
    "LipSyncDispatchResponse",
    "LipSyncJobResponse",
    "RenderLipSyncProjectRequest",
    "RenderSegmentLipSyncRequest",
    "ReplicateWebhookPayload",
]:
    setattr(app_schemas_lipsync_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.lipsync_schema", app_schemas_lipsync_module)

app_schemas_export_module = types.ModuleType("app.schemas.export_schema")
for name in ["ExportDispatchResponse", "ExportJobResponse", "ExportRequest"]:
    setattr(app_schemas_export_module, name, type(name, (BaseModel,), {}))
sys.modules.setdefault("app.schemas.export_schema", app_schemas_export_module)

app_services_media_module = types.ModuleType("app.services.media_service")
app_services_media_module.media_service = SimpleNamespace(
    generate_storage_key=lambda filename: f"uploads/{filename}",
    probe_media_file=None,
    generate_thumbnail=None,
)
sys.modules.setdefault("app.services.media_service", app_services_media_module)

app_services_storage_module = types.ModuleType("app.services.storage_service")
app_services_storage_module.storage_service = SimpleNamespace(
    generate_presigned_download_url=lambda *args, **kwargs: "https://example.test/file",
    create_resumable_upload_url=lambda *args, **kwargs: "https://example.test/upload",
    initiate_multipart_upload=lambda *args, **kwargs: "upload-1",
    object_exists=lambda *args, **kwargs: True,
    download_file=None,
    upload_part=lambda *args, **kwargs: "etag",
)
sys.modules.setdefault("app.services.storage_service", app_services_storage_module)

app_services_cloud_tasks_module = types.ModuleType("app.services.cloud_tasks_service")
app_services_cloud_tasks_module.cloud_tasks_service = SimpleNamespace(enabled=False, enqueue_http_task=lambda **kwargs: None)
sys.modules.setdefault("app.services.cloud_tasks_service", app_services_cloud_tasks_module)

app_services_pipeline_module = types.ModuleType("app.services.pipeline_availability")
app_services_pipeline_module.require_background_pipelines = lambda: None
sys.modules.setdefault("app.services.pipeline_availability", app_services_pipeline_module)

app_services_translation_service_module = types.ModuleType("app.services.translation_service")
app_services_translation_service_module.translation_service = SimpleNamespace(translate_segments_batch_async=None)
sys.modules.setdefault("app.services.translation_service", app_services_translation_service_module)

app_services_duration_matcher_module = types.ModuleType("app.services.duration_matcher")
app_services_duration_matcher_module.duration_matcher = SimpleNamespace()
sys.modules.setdefault("app.services.duration_matcher", app_services_duration_matcher_module)

app_services_tts_orchestrator_module = types.ModuleType("app.services.tts_orchestrator")
app_services_tts_orchestrator_module.tts_orchestrator = SimpleNamespace(
    synthesize_single_translation=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("TTS should not run"))
)
sys.modules.setdefault("app.services.tts_orchestrator", app_services_tts_orchestrator_module)

app_services_export_queue_module = types.ModuleType("app.services.export_queue_manager")
app_services_export_queue_module.export_queue_manager = SimpleNamespace()
sys.modules.setdefault("app.services.export_queue_manager", app_services_export_queue_module)

app_utils_transcript_parser_module = types.ModuleType("app.utils.transcript_parser")
app_utils_transcript_parser_module.transcript_parser = SimpleNamespace()
sys.modules.setdefault("app.utils.transcript_parser", app_utils_transcript_parser_module)

app_utils_language_configs_module = types.ModuleType("app.utils.language_configs")
app_utils_language_configs_module.get_supported_languages = lambda: []
sys.modules.setdefault("app.utils.language_configs", app_utils_language_configs_module)

app_utils_speech_rate_module = types.ModuleType("app.utils.speech_rate")
app_utils_speech_rate_module.speech_rate_estimator = SimpleNamespace()
sys.modules.setdefault("app.utils.speech_rate", app_utils_speech_rate_module)

app_utils_file_validators_module = types.ModuleType("app.utils.file_validators")
app_utils_file_validators_module.calculate_sha256 = lambda *_args, **_kwargs: "checksum"
app_utils_file_validators_module.detect_mime_type_from_header = lambda *_args, **_kwargs: "video/mp4"
app_utils_file_validators_module.validate_file_metadata = lambda *_args, **_kwargs: None
sys.modules.setdefault("app.utils.file_validators", app_utils_file_validators_module)

app_utils_error_codes_module = types.ModuleType("app.utils.error_codes")


class MediaAppException(HTTPException):
    def __init__(self, status_code: int, error_code=None, message: str = "", details=None):
        super().__init__(status_code=status_code, detail=message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}


class FileTooLargeException(MediaAppException):
    pass


class ChecksumMismatchException(MediaAppException):
    pass


class UploadSessionExpiredException(MediaAppException):
    pass


app_utils_error_codes_module.MediaAppException = MediaAppException
app_utils_error_codes_module.FileTooLargeException = FileTooLargeException
app_utils_error_codes_module.ChecksumMismatchException = ChecksumMismatchException
app_utils_error_codes_module.UploadSessionExpiredException = UploadSessionExpiredException
app_utils_error_codes_module.ErrorCode = SimpleNamespace(
    INVALID_FORMAT="INVALID_FORMAT",
    UPLOAD_SESSION_NOT_FOUND="UPLOAD_SESSION_NOT_FOUND",
    STORAGE_UPLOAD_FAILED="STORAGE_UPLOAD_FAILED",
    CHUNK_TOO_SMALL="CHUNK_TOO_SMALL",
)
sys.modules.setdefault("app.utils.error_codes", app_utils_error_codes_module)

app_tasks_transcription_module = types.ModuleType("app.tasks.transcription_tasks")
app_tasks_transcription_module.preprocess_and_transcribe_pipeline_task = SimpleNamespace(apply_async=lambda **kwargs: SimpleNamespace(id="task-1"))
sys.modules.setdefault("app.tasks.transcription_tasks", app_tasks_transcription_module)

app_tasks_tts_module = types.ModuleType("app.tasks.tts_tasks")
app_tasks_tts_module.synthesize_project_tts_task = SimpleNamespace(apply_async=lambda **kwargs: SimpleNamespace(id="task-2"))
sys.modules.setdefault("app.tasks.tts_tasks", app_tasks_tts_module)

app_tasks_lipsync_module = types.ModuleType("app.tasks.lipsync_tasks")
app_tasks_lipsync_module.render_lipsync_project_task = SimpleNamespace(apply_async=lambda **kwargs: SimpleNamespace(id="task-3"))
sys.modules.setdefault("app.tasks.lipsync_tasks", app_tasks_lipsync_module)

app_tasks_export_module = types.ModuleType("app.tasks.export_tasks")
app_tasks_export_module.render_video_export_task = SimpleNamespace(apply_async=lambda **kwargs: SimpleNamespace(id="task-4"))
sys.modules.setdefault("app.tasks.export_tasks", app_tasks_export_module)

from app.routers import export, lipsync, transcription, translation, tts, upload


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return self._value
        return [self._value]


class FakeAsyncSession:
    def __init__(self, *results):
        self._results = list(results)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        value = self._results.pop(0) if self._results else None
        return _ScalarResult(value)

    def add(self, value):
        return None

    async def commit(self):
        return None

    async def refresh(self, value):
        return None

    async def flush(self):
        return None

    async def delete(self, value):
        return None


def _build_context(role: str = "editor") -> AuthenticatedRequestContext:
    return AuthenticatedRequestContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=role,
    )


def test_upload_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    upload_id = uuid.uuid4()
    session = SimpleNamespace(
        id=upload_id,
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        chunks=[],
        total_chunks=1,
        bytes_received=0,
        filesize_bytes=1,
        filename="demo.mp4",
        status="in_progress",
        expires_at=None,
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == session.workspace_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(upload, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload.get_resumable_upload_status(upload_id=upload_id, context=context, db=FakeAsyncSession(session)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Upload session not found."


def test_transcription_get_transcript_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    transcript_id = uuid.uuid4()
    transcript_row = SimpleNamespace(
        id=transcript_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        segments=[],
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == transcript_row.workspace_id
        assert kwargs["project_id"] == transcript_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(transcription.get_transcript(transcript_id=transcript_id, context=context, db=FakeAsyncSession(transcript_row)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transcript not found."


def test_translation_translate_project_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    transcript_id = uuid.uuid4()
    transcript_row = SimpleNamespace(
        id=transcript_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        detected_language="en",
    )
    req = SimpleNamespace(transcript_id=transcript_id, source_language=None, target_language="es")

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == transcript_row.workspace_id
        assert kwargs["project_id"] == transcript_row.project_id
        assert kwargs["require_write"] is True
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(translation, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(translation.translate_project(req=req, context=context, db=FakeAsyncSession(transcript_row)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transcript not found."


def test_tts_synthesize_segment_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    translation_id = uuid.uuid4()
    translation_row = SimpleNamespace(
        id=translation_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    req = SimpleNamespace(translation_id=translation_id)

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == translation_row.workspace_id
        assert kwargs["project_id"] == translation_row.project_id
        assert kwargs["require_write"] is True
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(tts, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(tts.synthesize_single_segment(req=req, context=context, db=FakeAsyncSession(translation_row)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Translation not found."


def test_lipsync_job_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    job_id = uuid.uuid4()
    job_row = SimpleNamespace(
        id=job_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        segments_metadata=[],
        output_video_gcs_path=None,
        target_language="es",
        model_name="liveportrait",
        status="queued",
        progress_percent=0,
        total_segments=0,
        completed_segments=0,
        quality_score=0.95,
        av_sync_error_ms=0.0,
        execution_time_seconds=None,
        media_file_id=uuid.uuid4(),
        created_at=None,
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == job_row.workspace_id
        assert kwargs["project_id"] == job_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(lipsync, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(lipsync.get_lipsync_job(job_id=job_id, context=context, db=FakeAsyncSession(job_row)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Lip-sync job not found."


def test_export_job_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    job_id = uuid.uuid4()
    job_row = SimpleNamespace(
        id=job_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == job_row.workspace_id
        assert kwargs["project_id"] == job_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(export, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(export.get_export_job_status(job_id=job_id, context=context, db=FakeAsyncSession(job_row)))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Export job not found."
