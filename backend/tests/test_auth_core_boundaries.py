from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.core.auth as auth_module
from app.core.auth import (
    AuthenticatedRequestContext,
    ensure_workspace_resource_access,
    get_request_context,
    get_scoped_project,
    require_workspace_write_context,
)
from app.schemas.auth import (
    AuthBootstrapResponse,
    AuthenticatedUserResponse,
    WorkspaceMembershipResponse,
    WorkspaceSummaryResponse,
)
from app.services.auth_service import AccountAccessError, WorkspaceAccessError


FIXED_NOW = datetime(2026, 9, 5, 18, 30, tzinfo=timezone.utc)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ProjectLookupSession:
    def __init__(self, *projects):
        self.projects = list(projects)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        params = stmt.compile().params
        project_id = params.get("id_1")
        workspace_id = params.get("workspace_id_1")

        for project in self.projects:
            if project.id == project_id and project.workspace_id == workspace_id:
                return _ScalarResult(project)
        return _ScalarResult(None)


def _request(headers=None, method="GET"):
    encoded_headers = [
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    ]
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/",
            "headers": encoded_headers,
            "query_string": b"",
        },
        receive,
    )


def _bootstrap_response(*, user_id: uuid.UUID, workspace_id: uuid.UUID, role: str = "owner"):
    return AuthBootstrapResponse(
        user=AuthenticatedUserResponse(
            id=user_id,
            email="person@example.com",
            display_name="Person",
            auth_provider="identity_platform",
            auth_subject="google-oauth2|1234567890",
            is_active=True,
            last_login_at=FIXED_NOW,
            created_at=FIXED_NOW,
            updated_at=FIXED_NOW,
        ),
        workspace=WorkspaceSummaryResponse(
            id=workspace_id,
            name="Person Personal Workspace",
            slug="person-personal",
            owner_user_id=user_id,
            is_personal=True,
            archived_at=None,
            created_at=FIXED_NOW,
            updated_at=FIXED_NOW,
        ),
        membership=WorkspaceMembershipResponse(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            invited_by_user_id=user_id,
            joined_at=FIXED_NOW,
            created_at=FIXED_NOW,
            updated_at=FIXED_NOW,
        ),
        bootstrap_completed=True,
    )


def _context(*, role: str = "editor", workspace_id: uuid.UUID | None = None) -> AuthenticatedRequestContext:
    user_id = uuid.uuid4()
    workspace_id = workspace_id or uuid.uuid4()
    bootstrap = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        workspace=SimpleNamespace(id=workspace_id),
        membership=SimpleNamespace(role=role),
    )
    return AuthenticatedRequestContext(bootstrap=bootstrap, auth_provider="identity_platform")


def _project(*, workspace_id: uuid.UUID, project_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=project_id or uuid.uuid4(),
        workspace_id=workspace_id,
        owner_user_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
        name="Scoped Project",
        slug="scoped-project",
        status="draft",
    )


@pytest.mark.asyncio
async def test_get_request_context_uses_debug_identity_defaults_and_workspace_override(monkeypatch):
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    bootstrap = _bootstrap_response(user_id=user_id, workspace_id=workspace_id)

    bootstrap_actor = AsyncMock(return_value=bootstrap)
    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", True)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    request = _request(
        {
            "X-Debug-User-Email": "Debug.User@Example.com",
            "X-Workspace-Id": str(workspace_id),
        }
    )

    context = await get_request_context(request=request, db=SimpleNamespace())

    assert context.auth_provider == "debug"
    assert context.bootstrap is bootstrap
    assert context.user_id == user_id
    assert context.workspace_id == workspace_id

    identity = bootstrap_actor.await_args.kwargs["identity"]
    assert identity.email == "debug.user@example.com"
    assert identity.display_name == "debug.user"
    assert identity.auth_subject == "debug.user@example.com"
    assert identity.auth_provider == "debug"
    assert identity.email_verified is True
    assert bootstrap_actor.await_args.kwargs["requested_workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_get_request_context_rejects_invalid_workspace_override_before_bootstrap(monkeypatch):
    bootstrap_actor = AsyncMock()
    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", True)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    request = _request(
        {
            "X-Debug-User-Email": "debug@example.com",
            "X-Workspace-Id": "not-a-uuid",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(request=request, db=SimpleNamespace())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "X-Workspace-Id must be a valid UUID."
    bootstrap_actor.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", ["Basic abc", "Bearer", "Bearer   "])
async def test_get_request_context_rejects_malformed_bearer_token(monkeypatch, authorization):
    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", False)

    request = _request({"Authorization": authorization})

    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(request=request, db=SimpleNamespace())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing bearer token."


@pytest.mark.asyncio
async def test_get_request_context_verifies_single_google_audience_and_normalizes_identity(monkeypatch):
    workspace_id = uuid.uuid4()
    bootstrap = _bootstrap_response(user_id=uuid.uuid4(), workspace_id=workspace_id)
    verify = MagicMock(
        return_value={
            "aud": "client-a",
            "email": "PERSON@EXAMPLE.COM",
            "name": "  Person Example  ",
            "sub": "subject-123",
            "email_verified": True,
        }
    )
    bootstrap_actor = AsyncMock(return_value=bootstrap)

    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", False)
    monkeypatch.setattr(auth_module.settings, "GOOGLE_OAUTH_CLIENT_IDS", ["client-a"])
    monkeypatch.setattr(auth_module.id_token, "verify_oauth2_token", verify)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    context = await get_request_context(
        request=_request({"Authorization": "Bearer identity-token"}),
        db=SimpleNamespace(),
    )

    assert context.auth_provider == auth_module.settings.AUTH_PROVIDER
    assert context.workspace_id == workspace_id
    assert verify.call_count == 1
    assert verify.call_args.args[2] == "client-a"

    identity = bootstrap_actor.await_args.kwargs["identity"]
    assert identity.email == "person@example.com"
    assert identity.display_name == "Person Example"
    assert identity.auth_subject == "subject-123"
    assert identity.auth_provider == auth_module.settings.AUTH_PROVIDER


@pytest.mark.asyncio
async def test_get_request_context_accepts_multi_audience_config_without_passing_audience_to_verifier(monkeypatch):
    workspace_id = uuid.uuid4()
    bootstrap = _bootstrap_response(user_id=uuid.uuid4(), workspace_id=workspace_id)
    verify = MagicMock(
        return_value={
            "aud": "client-b",
            "email": "person@example.com",
            "name": "Person",
            "sub": "subject-456",
            "email_verified": True,
        }
    )
    bootstrap_actor = AsyncMock(return_value=bootstrap)

    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", False)
    monkeypatch.setattr(auth_module.settings, "GOOGLE_OAUTH_CLIENT_IDS", ["client-a", "client-b"])
    monkeypatch.setattr(auth_module.id_token, "verify_oauth2_token", verify)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    context = await get_request_context(
        request=_request({"Authorization": "Bearer identity-token"}),
        db=SimpleNamespace(),
    )

    assert context.workspace_id == workspace_id
    assert verify.call_args.args[0] == "identity-token"
    assert len(verify.call_args.args) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claims", "detail"),
    [
        ({"aud": "client-a", "email_verified": True, "sub": "subject-123"}, "Identity token is missing required subject or email claims."),
        ({"aud": "client-a", "email": "person@example.com", "email_verified": True}, "Identity token is missing required subject or email claims."),
        ({"aud": "client-a", "email": "person@example.com", "sub": "subject-123", "email_verified": False}, "Identity token email must be verified."),
    ],
)
async def test_get_request_context_rejects_google_claim_errors(monkeypatch, claims, detail):
    bootstrap_actor = AsyncMock()
    verify = MagicMock(return_value=claims)

    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", False)
    monkeypatch.setattr(auth_module.settings, "GOOGLE_OAUTH_CLIENT_IDS", ["client-a"])
    monkeypatch.setattr(auth_module.id_token, "verify_oauth2_token", verify)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(
            request=_request({"Authorization": "Bearer identity-token"}),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == detail
    bootstrap_actor.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_request_context_rejects_google_token_verification_errors(monkeypatch):
    bootstrap_actor = AsyncMock()
    verify = MagicMock(side_effect=ValueError("bad token"))

    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", False)
    monkeypatch.setattr(auth_module.settings, "GOOGLE_OAUTH_CLIENT_IDS", ["client-a"])
    monkeypatch.setattr(auth_module.id_token, "verify_oauth2_token", verify)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(
            request=_request({"Authorization": "Bearer identity-token"}),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unable to verify identity token."
    bootstrap_actor.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (AccountAccessError("account blocked"), "account blocked"),
        (WorkspaceAccessError("workspace blocked"), "workspace blocked"),
    ],
)
async def test_get_request_context_translates_bootstrap_errors_to_forbidden(monkeypatch, error, detail):
    bootstrap_actor = AsyncMock(side_effect=error)
    monkeypatch.setattr(auth_module.settings, "ALLOW_INSECURE_DEV_AUTH", True)
    monkeypatch.setattr(auth_module.auth_service, "bootstrap_actor_context", bootstrap_actor)

    with pytest.raises(HTTPException) as exc_info:
        await get_request_context(
            request=_request({"X-Debug-User-Email": "debug@example.com"}),
            db=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == detail


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "editor"])
async def test_require_workspace_write_context_allows_workspace_write_roles(role):
    context = _context(role=role)

    result = await require_workspace_write_context(context)

    assert result is context


@pytest.mark.asyncio
async def test_require_workspace_write_context_rejects_viewer():
    context = _context(role="viewer")

    with pytest.raises(HTTPException) as exc_info:
        await require_workspace_write_context(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Workspace membership role does not allow this operation."


@pytest.mark.asyncio
async def test_get_scoped_project_enforces_workspace_boundary_and_write_guard():
    workspace_id = uuid.uuid4()
    other_workspace_id = uuid.uuid4()
    project_id = uuid.uuid4()
    project = _project(workspace_id=workspace_id, project_id=project_id)
    db = _ProjectLookupSession(project)
    context = _context(role="editor", workspace_id=workspace_id)

    result = await get_scoped_project(
        project_id=project_id,
        db=db,
        context=context,
        require_write=True,
        not_found_detail="Project not found.",
    )

    assert result is project
    compiled = str(db.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert project_id.hex in compiled
    assert workspace_id.hex in compiled

    with pytest.raises(HTTPException) as exc_info:
        await get_scoped_project(
            project_id=project_id,
            db=_ProjectLookupSession(project),
            context=_context(role="editor", workspace_id=other_workspace_id),
            not_found_detail="Project not found.",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found."


@pytest.mark.asyncio
async def test_get_scoped_project_rejects_viewer_before_db_lookup():
    project = _project(workspace_id=uuid.uuid4())

    class _FailingSession:
        async def execute(self, stmt):
            raise AssertionError("scope check should fail before the database is queried")

    with pytest.raises(HTTPException) as exc_info:
        await get_scoped_project(
            project_id=project.id,
            db=_FailingSession(),
            context=_context(role="viewer", workspace_id=project.workspace_id),
            require_write=True,
            not_found_detail="Project not found.",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Workspace membership role does not allow this operation."


@pytest.mark.asyncio
async def test_ensure_workspace_resource_access_rejects_cross_workspace_workspace_scope():
    context = _context()
    other_workspace_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await ensure_workspace_resource_access(
            db=_ProjectLookupSession(),
            context=context,
            workspace_id=other_workspace_id,
            not_found_detail="Resource not found.",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Resource not found."
