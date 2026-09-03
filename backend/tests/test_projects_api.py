import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import get_request_context
from app.core.database import get_db
from app.routers.projects import router
from app.schemas.projects import DraftConflictErrorDetail
from app.services.project_service import ProjectDraftConflictError, ProjectNotFoundError, ProjectService


WORKSPACE_ID = "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5"
PROJECT_ID = "6f3d1f27-4fd4-4ca7-a3e7-6cf1f9e93b31"
ACTOR_USER_ID = "1c8d8f92-62d1-4619-98d0-45bd63a48617"
TRANSCRIPT_ID = "40f0b93d-ea1a-43ec-83d9-56064d9b8698"
MEDIA_FILE_ID = "7db6c44c-d1ab-4f77-a0ab-f4af5d471a90"
TIMESTAMP = "2026-08-29T09:42:10Z"
ARCHIVED_AT = "2026-08-29T10:02:33Z"


api_app = FastAPI()
api_app.include_router(router, prefix="/v1")


async def _dummy_get_db():
    yield AsyncMock(name="db_session")


def _build_request_context(role: str = "owner"):
    return SimpleNamespace(
        user_id=uuid.UUID(ACTOR_USER_ID),
        workspace_id=uuid.UUID(WORKSPACE_ID),
        membership_role=role,
    )


async def _dummy_request_context():
    return _build_request_context()


api_app.dependency_overrides[get_db] = _dummy_get_db
api_app.dependency_overrides[get_request_context] = _dummy_request_context


@pytest.fixture
def mock_project_service():
    with patch("app.routers.projects.project_service") as mock_service:
        mock_service.list_projects = AsyncMock()
        mock_service.create_project = AsyncMock()
        mock_service.get_project = AsyncMock()
        mock_service.get_pipeline_operation = AsyncMock()
        mock_service.update_project = AsyncMock()
        mock_service.get_project_draft = AsyncMock()
        mock_service.put_project_draft = AsyncMock()
        mock_service.archive_project = AsyncMock()
        mock_service.duplicate_project = AsyncMock()
        mock_service.list_project_versions = AsyncMock()
        mock_service.get_project_version = AsyncMock()
        yield mock_service


@pytest.fixture
def project_summary_response():
    return {
        "id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "owner_user_id": ACTOR_USER_ID,
        "name": "Hindi Product Launch",
        "status": "draft",
        "source_language": "en",
        "target_language": "hi",
        "active_translation_language": "hi",
        "media_file_id": MEDIA_FILE_ID,
        "transcript_id": TRANSCRIPT_ID,
        "latest_draft_version": 1,
        "last_rendered_video_gcs_path": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }


@pytest.fixture
def project_detail_response():
    return {
        "id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "owner_user_id": ACTOR_USER_ID,
        "created_by_user_id": ACTOR_USER_ID,
        "name": "Hindi Product Launch",
        "slug": None,
        "status": "draft",
        "source_language": "en",
        "target_language": "hi",
        "active_translation_language": "hi",
        "media_file_id": MEDIA_FILE_ID,
        "transcript_id": TRANSCRIPT_ID,
        "current_lipsync_job_id": None,
        "current_export_job_id": None,
        "last_rendered_video_gcs_path": None,
        "latest_draft_version": 1,
        "archived_at": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }


@pytest.fixture
def project_draft_response():
    return {
        "project_id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "version": 1,
        "draft_schema_version": "heygenx/v1",
        "base_project_updated_at": TIMESTAMP,
        "last_saved_by_user_id": ACTOR_USER_ID,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "draft_payload": {
            "version": "heygenx/v1",
            "projectMetadata": {
                "id": PROJECT_ID,
                "name": "Hindi Product Launch",
                "sourceLanguage": "en",
                "targetLanguage": "hi",
                "status": "draft",
            },
        },
    }


@pytest.mark.asyncio
async def test_list_projects_returns_workspace_scoped_items(mock_project_service, project_summary_response):
    mock_project_service.list_projects.return_value = {
        "items": [project_summary_response],
        "next_cursor": None,
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/projects",
            params={
                "status": "draft",
                "limit": 20,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == PROJECT_ID
    assert payload["items"][0]["owner_user_id"] == ACTOR_USER_ID
    assert "original_media_url" not in payload["items"][0]
    assert "last_rendered_video_url" not in payload["items"][0]
    assert mock_project_service.list_projects.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.list_projects.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


def test_project_cursor_round_trip():
    project = SimpleNamespace(
        id=uuid.UUID(PROJECT_ID),
        updated_at=datetime(2026, 8, 29, 9, 42, 10, tzinfo=timezone.utc),
    )

    cursor = ProjectService._encode_project_cursor(project)
    updated_at, project_id = ProjectService._decode_project_cursor(cursor)

    assert updated_at == project.updated_at
    assert project_id == project.id


def test_invalid_project_cursor_is_rejected():
    with pytest.raises(ValueError, match="Invalid project cursor"):
        ProjectService._decode_project_cursor("invalid")


@pytest.mark.asyncio
async def test_create_project_creates_actor_scoped_shell(mock_project_service, project_detail_response):
    mock_project_service.create_project.return_value = project_detail_response

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/projects",
            json={
                "name": "Hindi Product Launch",
                "source_language": "en",
                "target_language": "hi",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workspace_id"] == WORKSPACE_ID
    assert payload["created_by_user_id"] == ACTOR_USER_ID
    assert mock_project_service.create_project.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.create_project.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_get_pipeline_operation_uses_workspace_scoped_project_access(mock_project_service):
    operation_id = str(uuid.uuid4())
    mock_project_service.get_pipeline_operation.return_value = {
        "id": operation_id,
        "project_id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "transcript_id": TRANSCRIPT_ID,
        "operation_type": "translation",
        "target_language": "hi",
        "status": "in_progress",
        "progress_percent": 30,
        "current_stage": "translate",
        "last_successful_stage": None,
        "message": "Translating segments",
        "error_message": None,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}/pipeline-operation")

    assert response.status_code == 200
    assert response.json()["operation_type"] == "translation"
    assert mock_project_service.get_pipeline_operation.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.get_pipeline_operation.await_args.kwargs["project_id"] == uuid.UUID(PROJECT_ID)


@pytest.mark.asyncio
async def test_create_project_rejects_viewer_role(mock_project_service):
    async def _viewer_request_context():
        return _build_request_context(role="viewer")

    api_app.dependency_overrides[get_request_context] = _viewer_request_context
    transport = ASGITransport(app=api_app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/projects",
                json={
                    "name": "Hindi Product Launch",
                    "source_language": "en",
                    "target_language": "hi",
                },
            )
    finally:
        api_app.dependency_overrides[get_request_context] = _dummy_request_context

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace membership role does not allow this operation."
    mock_project_service.create_project.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_project_returns_project_detail(mock_project_service, project_detail_response):
    mock_project_service.get_project.return_value = project_detail_response

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == PROJECT_ID
    assert "original_media_url" not in payload
    assert "last_rendered_video_url" not in payload
    assert mock_project_service.get_project.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.get_project.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_update_project_patches_mutable_metadata(mock_project_service, project_detail_response):
    updated_response = {**project_detail_response, "name": "Hindi Product Launch v2", "status": "processing"}
    mock_project_service.update_project.return_value = updated_response

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/v1/projects/{PROJECT_ID}",
            json={"name": "Hindi Product Launch v2", "status": "processing"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Hindi Product Launch v2"
    assert payload["status"] == "processing"
    assert mock_project_service.update_project.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.update_project.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_get_project_draft_returns_latest_saved_draft(mock_project_service, project_draft_response):
    mock_project_service.get_project_draft.return_value = project_draft_response

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}/draft")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["draft_payload"]["projectMetadata"]["id"] == PROJECT_ID
    assert mock_project_service.get_project_draft.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.get_project_draft.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_put_project_draft_returns_conflict_payload(mock_project_service):
    mock_project_service.put_project_draft.side_effect = ProjectDraftConflictError(
        DraftConflictErrorDetail(
            project_id=uuid.UUID(PROJECT_ID),
            client_version=1,
            server_version=2,
            server_updated_at=datetime(2026, 8, 29, 9, 42, 10, tzinfo=timezone.utc),
            last_saved_by_user_id=uuid.UUID(ACTOR_USER_ID),
        )
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/v1/projects/{PROJECT_ID}/draft",
            json={
                "version": 1,
                "draft_schema_version": "heygenx/v1",
                "base_project_updated_at": TIMESTAMP,
                "draft_payload": {"version": "heygenx/v1", "projectMetadata": {"id": PROJECT_ID}},
            },
        )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "DRAFT_VERSION_CONFLICT"
    assert payload["error"]["server_version"] == 2
    assert mock_project_service.put_project_draft.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.put_project_draft.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_archive_project_marks_project_archived(mock_project_service):
    mock_project_service.archive_project.return_value = {
        "id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "status": "archived",
        "archived_at": ARCHIVED_AT,
        "updated_at": ARCHIVED_AT,
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/v1/projects/{PROJECT_ID}/archive")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "archived"
    assert payload["archived_at"] == ARCHIVED_AT
    assert mock_project_service.archive_project.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.archive_project.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_duplicate_project_creates_workspace_scoped_shell(mock_project_service, project_detail_response):
    mock_project_service.duplicate_project.return_value = {
        **project_detail_response,
        "id": str(uuid.uuid4()),
        "name": "Hindi Product Launch copy",
        "status": "draft",
        "media_file_id": None,
        "transcript_id": None,
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/v1/projects/{PROJECT_ID}/duplicate")

    assert response.status_code == 201
    assert response.json()["name"] == "Hindi Product Launch copy"
    assert response.json()["media_file_id"] is None
    assert mock_project_service.duplicate_project.await_args.kwargs["project_id"] == uuid.UUID(PROJECT_ID)
    assert mock_project_service.duplicate_project.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)


@pytest.mark.asyncio
async def test_list_project_versions_is_workspace_scoped(mock_project_service):
    mock_project_service.list_project_versions.return_value = {
        "items": [
            {
                "version": 5,
                "draft_schema_version": "heygenx/v1",
                "created_by_user_id": ACTOR_USER_ID,
                "created_at": TIMESTAMP,
            },
            {
                "version": 3,
                "draft_schema_version": "heygenx/v1",
                "created_by_user_id": ACTOR_USER_ID,
                "created_at": TIMESTAMP,
            },
        ],
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}/versions")

    assert response.status_code == 200
    assert [item["version"] for item in response.json()["items"]] == [5, 3]
    assert "draft_payload" not in response.json()["items"][0]
    assert mock_project_service.list_project_versions.await_args.kwargs["workspace_id"] == uuid.UUID(WORKSPACE_ID)
    assert mock_project_service.list_project_versions.await_args.kwargs["actor_user_id"] == uuid.UUID(ACTOR_USER_ID)


@pytest.mark.asyncio
async def test_get_project_version_returns_full_snapshot(mock_project_service):
    mock_project_service.get_project_version.return_value = {
        "version": 3,
        "draft_schema_version": "heygenx/v1",
        "draft_payload": {"projectMetadata": {"id": PROJECT_ID}},
        "created_by_user_id": ACTOR_USER_ID,
        "created_at": TIMESTAMP,
    }

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}/versions/3")

    assert response.status_code == 200
    assert response.json()["draft_payload"]["projectMetadata"]["id"] == PROJECT_ID
    assert mock_project_service.get_project_version.await_args.kwargs["project_id"] == uuid.UUID(PROJECT_ID)
    assert mock_project_service.get_project_version.await_args.kwargs["version_number"] == 3


@pytest.mark.asyncio
async def test_get_project_returns_404_when_missing(mock_project_service):
    mock_project_service.get_project.side_effect = ProjectNotFoundError("Project not found.")

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/v1/projects/{PROJECT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."
