from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.auth import get_request_context
from app.core.database import get_db
from app.routers.auth import router
from app.services.auth_service import auth_service
from app.schemas.auth import WorkspaceListResponse, WorkspaceMemberListResponse, WorkspaceMemberResponse

USER_ID = "1c8d8f92-62d1-4619-98d0-45bd63a48617"
WORKSPACE_ID = "4e7e4b2e-0cf5-4cf5-983f-d4dded7fb5e5"
TIMESTAMP = "2026-08-29T09:42:10Z"

api_app = FastAPI()
api_app.include_router(router, prefix="/v1")


async def _dummy_request_context():
    return SimpleNamespace(
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        bootstrap={
            "user": {
                "id": USER_ID,
                "email": "namrata@example.com",
                "display_name": "Namrata",
                "auth_provider": "identity_platform",
                "auth_subject": "google-oauth2|1234567890",
                "is_active": True,
                "last_login_at": TIMESTAMP,
                "created_at": TIMESTAMP,
                "updated_at": TIMESTAMP,
            },
            "workspace": {
                "id": WORKSPACE_ID,
                "name": "Namrata Personal Workspace",
                "slug": "namrata-personal",
                "owner_user_id": USER_ID,
                "is_personal": True,
                "archived_at": None,
                "created_at": TIMESTAMP,
                "updated_at": TIMESTAMP,
            },
            "membership": {
                "workspace_id": WORKSPACE_ID,
                "user_id": USER_ID,
                "role": "owner",
                "invited_by_user_id": USER_ID,
                "joined_at": TIMESTAMP,
                "created_at": TIMESTAMP,
                "updated_at": TIMESTAMP,
            },
            "bootstrap_completed": True,
        },
        auth_provider="identity_platform",
    )


api_app.dependency_overrides[get_request_context] = _dummy_request_context


@pytest.mark.asyncio
async def test_bootstrap_authenticated_context_returns_user_workspace_scope():
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/auth/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == USER_ID
    assert payload["workspace"]["id"] == WORKSPACE_ID
    assert payload["membership"]["role"] == "owner"
    assert payload["bootstrap_completed"] is True


@pytest.mark.asyncio
async def test_get_authenticated_context_returns_bootstrapped_actor():
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "namrata@example.com"
    assert payload["workspace"]["name"] == "Namrata Personal Workspace"


@pytest.mark.asyncio
async def test_list_workspaces_uses_authenticated_user_scope():
    workspace_response = WorkspaceListResponse(items=[])
    service_mock = AsyncMock(return_value=workspace_response)
    db = object()
    api_app.dependency_overrides[get_db] = lambda: db
    original = auth_service.list_workspace_contexts
    auth_service.list_workspace_contexts = service_mock

    try:
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/auth/workspaces")
    finally:
        auth_service.list_workspace_contexts = original
        api_app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json() == {"items": []}
    service_mock.assert_awaited_once_with(db=db, user_id=USER_ID)


@pytest.mark.asyncio
async def test_list_workspace_members_uses_active_workspace_scope():
    member_response = WorkspaceMemberListResponse(
        items=[
            WorkspaceMemberResponse(
                user_id=USER_ID,
                display_name="Namrata",
                email="namrata@example.com",
                role="owner",
            )
        ]
    )
    service_mock = AsyncMock(return_value=member_response)
    db = object()
    api_app.dependency_overrides[get_db] = lambda: db
    original = auth_service.list_workspace_members
    auth_service.list_workspace_members = service_mock

    try:
        transport = ASGITransport(app=api_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/auth/workspace-members")
    finally:
        auth_service.list_workspace_members = original
        api_app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.json()["items"][0]["role"] == "owner"
    service_mock.assert_awaited_once_with(db=db, workspace_id=WORKSPACE_ID)
