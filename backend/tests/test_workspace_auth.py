import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
import sys
import types
import uuid

import pytest
from fastapi import HTTPException


sqlalchemy_module = types.ModuleType("sqlalchemy")
sqlalchemy_module.select = lambda *args, **kwargs: ("select", args, kwargs)
sys.modules.setdefault("sqlalchemy", sqlalchemy_module)

sqlalchemy_ext_module = types.ModuleType("sqlalchemy.ext")
sqlalchemy_ext_asyncio_module = types.ModuleType("sqlalchemy.ext.asyncio")
sqlalchemy_ext_asyncio_module.AsyncSession = object
sys.modules.setdefault("sqlalchemy.ext", sqlalchemy_ext_module)
sys.modules.setdefault("sqlalchemy.ext.asyncio", sqlalchemy_ext_asyncio_module)

google_auth_transport_module = types.ModuleType("google.auth.transport.requests")
google_auth_transport_module.Request = object
sys.modules.setdefault("google.auth.transport.requests", google_auth_transport_module)

google_oauth_id_token_module = types.ModuleType("google.oauth2.id_token")
google_oauth_id_token_module.verify_oauth2_token = lambda *args, **kwargs: {}
sys.modules.setdefault("google.oauth2.id_token", google_oauth_id_token_module)

app_core_config_module = types.ModuleType("app.core.config")
app_core_config_module.settings = SimpleNamespace(
    AUTH_PROVIDER="debug",
    ALLOW_INSECURE_DEV_AUTH=True,
    GOOGLE_OAUTH_CLIENT_IDS=[],
)
sys.modules.setdefault("app.core.config", app_core_config_module)

app_core_database_module = types.ModuleType("app.core.database")
app_core_database_module.get_db = lambda: None
sys.modules.setdefault("app.core.database", app_core_database_module)

app_models_project_module = types.ModuleType("app.models.project")


@dataclass
class ProjectStub:
    id: uuid.UUID
    workspace_id: uuid.UUID
    owner_user_id: uuid.UUID
    created_by_user_id: uuid.UUID
    name: str
    status: str


app_models_project_module.Project = ProjectStub
sys.modules.setdefault("app.models.project", app_models_project_module)

app_schemas_auth_module = types.ModuleType("app.schemas.auth")
app_schemas_auth_module.AuthBootstrapResponse = object
app_schemas_auth_module.WorkspaceRole = str
sys.modules.setdefault("app.schemas.auth", app_schemas_auth_module)

app_services_auth_service_module = types.ModuleType("app.services.auth_service")


class WorkspaceAccessError(Exception):
    pass


@dataclass
class ResolvedIdentity:
    email: str
    display_name: str | None
    auth_subject: str
    auth_provider: str
    email_verified: bool


app_services_auth_service_module.WorkspaceAccessError = WorkspaceAccessError
app_services_auth_service_module.ResolvedIdentity = ResolvedIdentity
app_services_auth_service_module.auth_service = SimpleNamespace(
    bootstrap_actor_context=None,
)
sys.modules.setdefault("app.services.auth_service", app_services_auth_service_module)

import app.core.auth as auth_module
from app.core.auth import AuthenticatedRequestContext, ensure_workspace_resource_access


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    def __init__(self, result):
        self._result = result
        self.last_stmt = None

    async def execute(self, stmt):
        self.last_stmt = stmt
        return _ScalarResult(self._result)


def _build_context(*, role: str = "editor") -> AuthenticatedRequestContext:
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    bootstrap = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        workspace=SimpleNamespace(id=workspace_id),
        membership=SimpleNamespace(role=role),
    )
    return AuthenticatedRequestContext(bootstrap=bootstrap, auth_provider="debug")


def test_resource_access_allows_matching_workspace_id():
    context = _build_context()

    asyncio.run(
        ensure_workspace_resource_access(
            db=FakeAsyncSession(None),
            context=context,
            workspace_id=context.workspace_id,
        )
    )


def test_resource_access_resolves_project_scope_when_workspace_missing(monkeypatch):
    context = _build_context()
    project_id = uuid.uuid4()
    project = ProjectStub(
        id=project_id,
        workspace_id=context.workspace_id,
        owner_user_id=context.user_id,
        created_by_user_id=context.user_id,
        name="Scoped Project",
        status="draft",
    )

    async def _fake_get_scoped_project(**kwargs):
        assert kwargs["project_id"] == project_id
        return project

    monkeypatch.setattr(auth_module, "get_scoped_project", _fake_get_scoped_project)

    asyncio.run(
        ensure_workspace_resource_access(
            db=FakeAsyncSession(project),
            context=context,
            project_id=project_id,
        )
    )


def test_resource_access_allows_legacy_user_fallback_for_unscoped_rows():
    context = _build_context()

    asyncio.run(
        ensure_workspace_resource_access(
            db=FakeAsyncSession(None),
            context=context,
            legacy_user_id=context.user_id,
        )
    )


def test_resource_access_returns_not_found_for_other_workspace():
    context = _build_context()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ensure_workspace_resource_access(
                db=FakeAsyncSession(None),
                context=context,
                workspace_id=uuid.uuid4(),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Resource not found."


def test_resource_access_requires_write_role_before_fallback_checks():
    context = _build_context(role="viewer")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ensure_workspace_resource_access(
                db=FakeAsyncSession(None),
                context=context,
                legacy_user_id=context.user_id,
                require_write=True,
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Workspace membership role does not allow this operation."


def test_resource_access_returns_not_found_when_project_scope_cannot_be_resolved(monkeypatch):
    context = _build_context()

    async def _fake_get_scoped_project(**kwargs):
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(auth_module, "get_scoped_project", _fake_get_scoped_project)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ensure_workspace_resource_access(
                db=FakeAsyncSession(None),
                context=context,
                project_id=uuid.uuid4(),
                not_found_detail="Transcript not found.",
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transcript not found."
