import asyncio
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

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
    project = SimpleNamespace(
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


def test_resource_access_returns_not_found_for_unscoped_rows():
    context = _build_context()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ensure_workspace_resource_access(
                db=FakeAsyncSession(None),
                context=context,
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Resource not found."


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


def test_resource_access_requires_write_role_before_scope_checks():
    context = _build_context(role="viewer")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ensure_workspace_resource_access(
                db=FakeAsyncSession(None),
                context=context,
                workspace_id=context.workspace_id,
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
