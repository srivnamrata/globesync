import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.schemas.projects import ProjectCreateRequest, ProjectListQueryParams, ProjectUpdateRequest
from app.services.project_service import ProjectNotFoundError, ProjectService


NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)
WORKSPACE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, scalar=None, values=None):
        self.scalar = scalar
        self.values = values or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return _Scalars(self.values)


class _Session:
    def __init__(self, *results, scalar_values=None):
        self.results = iter(results)
        self.scalar_values = iter(scalar_values or [])
        self.added = []

    async def execute(self, _statement):
        return next(self.results)

    async def scalar(self, _statement):
        return next(self.scalar_values)

    def add(self, entity):
        self.added.append(entity)

    async def flush(self):
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid.uuid4()
            if getattr(entity, "slug", None) is None and entity.__class__.__name__ == "Project":
                entity.slug = f"project-{str(entity.id)[:8]}"
            if hasattr(entity, "created_at") and entity.created_at is None:
                entity.created_at = NOW
            if hasattr(entity, "updated_at") and entity.updated_at is None:
                entity.updated_at = NOW

    async def refresh(self, _entity):
        await self.flush()


def _project(**overrides):
    values = {
        "id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "owner_user_id": USER_ID,
        "created_by_user_id": USER_ID,
        "name": "Project",
        "slug": "project",
        "status": "draft",
        "source_language": "en",
        "target_language": "es",
        "active_translation_language": "es",
        "media_file_id": None,
        "transcript_id": None,
        "current_lipsync_job_id": None,
        "current_export_job_id": None,
        "current_pipeline_operation_id": None,
        "last_rendered_video_gcs_path": None,
        "archived_at": None,
        "last_opened_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "media_file": None,
        "current_export_job": None,
        "current_lipsync_job": None,
    }
    values.update(overrides)
    project = SimpleNamespace(**values)
    project.__dict__["draft"] = overrides.get("draft")
    return project


@pytest.mark.asyncio
async def test_project_create_get_update_archive_and_duplicate_cover_state_transitions():
    service = ProjectService()
    service._utcnow = lambda: NOW

    create_session = _Session()
    created = await service.create_project(
        create_session,
        WORKSPACE_ID,
        ProjectCreateRequest(name="Launch", source_language="en", target_language="es"),
        USER_ID,
    )
    assert created.name == "Launch"
    assert created.status == "draft"
    assert created.latest_draft_version == 0

    project = _project(status="archived", archived_at=NOW)
    media_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    lipsync_id = uuid.uuid4()
    export_id = uuid.uuid4()
    update_session = _Session(_Result(project))
    updated = await service.update_project(
        update_session,
        WORKSPACE_ID,
        PROJECT_ID,
        ProjectUpdateRequest(
            name="Updated",
            status="processing",
            source_language="fr",
            target_language="de",
            active_translation_language="de",
            media_file_id=media_id,
            transcript_id=transcript_id,
            current_lipsync_job_id=lipsync_id,
            current_export_job_id=export_id,
            last_rendered_video_gcs_path="gs://bucket/final.mp4",
        ),
        USER_ID,
    )
    assert updated.status == "processing"
    assert updated.archived_at is None
    assert updated.media_file_id == media_id
    assert updated.current_export_job_id == export_id

    fetched = await service.get_project(
        _Session(_Result(project)), WORKSPACE_ID, PROJECT_ID, USER_ID
    )
    assert fetched.name == "Updated"

    archived = await service.archive_project(
        _Session(_Result(project)), WORKSPACE_ID, PROJECT_ID, USER_ID
    )
    assert archived.status == "archived"
    assert archived.archived_at == NOW

    duplicated_session = _Session(_Result(project))
    duplicate = await service.duplicate_project(
        duplicated_session, WORKSPACE_ID, PROJECT_ID, USER_ID
    )
    assert duplicate.name == "Updated copy"
    assert duplicate.status == "draft"
    assert duplicate.owner_user_id == USER_ID
    assert duplicate.media_file_id is None
    assert duplicate.transcript_id is None


@pytest.mark.asyncio
async def test_project_list_maps_media_and_pipeline_status_and_cursor():
    service = ProjectService()
    media = SimpleNamespace(original_filename="clip.mp4", duration_seconds=9.5)
    export_job = SimpleNamespace(
        current_stage="muxing_video",
        status="processing",
        progress_percent=75,
        error_message=None,
    )
    first = _project(
        id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        updated_at=NOW,
        media_file=media,
        media_file_id=MEDIA_ID if (MEDIA_ID := uuid.uuid4()) else None,
        current_export_job=export_job,
        draft=SimpleNamespace(version=4),
    )
    second = _project(
        id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        name="Second",
        updated_at=NOW,
        current_lipsync_job=SimpleNamespace(
            current_stage="render_faces",
            status="failed",
            progress_percent=20,
            error_message="render failed",
        ),
    )
    session = _Session(_Result(values=[first, second]))

    result = await service.list_projects(
        session,
        WORKSPACE_ID,
        USER_ID,
        ProjectListQueryParams(status="draft", limit=1, include_archived=True),
    )

    assert len(result.items) == 1
    assert result.items[0].media_filename == "clip.mp4"
    assert result.items[0].pipeline_stage == "Export: muxing video"
    assert result.items[0].latest_draft_version == 4
    assert result.next_cursor
    decoded_at, decoded_id = service._decode_project_cursor(result.next_cursor)
    assert decoded_at == NOW
    assert decoded_id == first.id


@pytest.mark.asyncio
async def test_project_operation_draft_and_version_boundaries():
    service = ProjectService()
    project = _project()

    with pytest.raises(ProjectNotFoundError, match="draft"):
        await service.get_project_draft(
            _Session(_Result(project)), WORKSPACE_ID, PROJECT_ID, USER_ID
        )

    with pytest.raises(ProjectNotFoundError, match="operation"):
        await service.get_pipeline_operation(
            _Session(_Result(project), scalar_values=[None]),
            WORKSPACE_ID,
            PROJECT_ID,
            USER_ID,
        )

    operation = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        transcript_id=uuid.uuid4(),
        operation_type="translation",
        target_language="es",
        status="failed",
        progress_percent=35,
        current_stage="translate",
        last_successful_stage="prepare",
        message="failed",
        error_message="provider error",
        created_at=NOW,
        updated_at=NOW,
    )
    project.current_pipeline_operation_id = operation.id
    response = await service.get_pipeline_operation(
        _Session(_Result(project), scalar_values=[operation]),
        WORKSPACE_ID,
        PROJECT_ID,
        USER_ID,
    )
    assert response.status == "failed"
    assert response.error_message == "provider error"

    with pytest.raises(ProjectNotFoundError, match="version"):
        await service.get_project_version(
            _Session(_Result(project), scalar_values=[None]),
            WORKSPACE_ID,
            PROJECT_ID,
            99,
            USER_ID,
        )


@pytest.mark.asyncio
async def test_project_versions_and_draft_response_preserve_snapshot_metadata():
    service = ProjectService()
    draft = SimpleNamespace(
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        version=3,
        draft_schema_version="globesync/v1",
        base_project_updated_at=NOW,
        last_saved_by_user_id=USER_ID,
        created_at=NOW,
        updated_at=NOW,
        draft_payload={"projectMetadata": {"custom": "preserved"}},
    )
    project = _project(
        draft=draft,
        media_file_id=uuid.uuid4(),
        transcript_id=uuid.uuid4(),
        media_file=SimpleNamespace(original_filename="source.mp4", duration_seconds=12.5),
    )
    response = await service.get_project_draft(
        _Session(_Result(project)), WORKSPACE_ID, PROJECT_ID, USER_ID
    )
    assert response.draft_payload["projectMetadata"]["custom"] == "preserved"
    assert response.draft_payload["projectMetadata"]["name"] == "Project"
    assert response.draft_payload["mediaReferences"]["videoFilename"] == "source.mp4"

    versions = [
        SimpleNamespace(
            version=3,
            draft_schema_version="globesync/v1",
            created_by_user_id=USER_ID,
            created_at=NOW,
        )
    ]
    listed = await service.list_project_versions(
        _Session(_Result(project), _Result(values=versions)),
        WORKSPACE_ID,
        PROJECT_ID,
        USER_ID,
    )
    assert listed.items[0].version == 3


@pytest.mark.asyncio
async def test_scoped_project_and_cursor_reject_missing_or_invalid_values():
    service = ProjectService()
    with pytest.raises(ProjectNotFoundError):
        await service._get_scoped_project(
            _Session(_Result(None)), WORKSPACE_ID, PROJECT_ID, USER_ID
        )
    with pytest.raises(ValueError, match="Invalid project cursor"):
        service._decode_project_cursor("not-a-cursor")

