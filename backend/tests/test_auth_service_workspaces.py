import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.identity import User, Workspace, WorkspaceMember
from app.services.auth_service import AuthService, ResolvedIdentity, WorkspaceAccessError


NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


class _Result:
    def __init__(self, *, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def all(self):
        return self.rows


class _Session:
    def __init__(self, *results):
        self.results = iter(results)
        self.added = []
        self.flush_count = 0

    async def execute(self, _statement):
        return next(self.results)

    def add(self, entity):
        self.added.append(entity)

    async def flush(self):
        self.flush_count += 1
        for entity in self.added:
            if entity.id is None:
                entity.id = uuid.uuid4()
            if hasattr(entity, "created_at") and entity.created_at is None:
                entity.created_at = NOW
            if hasattr(entity, "updated_at") and entity.updated_at is None:
                entity.updated_at = NOW


def _identity(subject="subject-1"):
    return ResolvedIdentity(
        email="new.user@example.com",
        display_name="New User",
        auth_subject=subject,
    )


@pytest.mark.asyncio
async def test_bootstrap_creates_user_personal_workspace_and_owner_membership():
    session = _Session(
        _Result(scalar=None),
        _Result(scalar=None),
        _Result(scalar=None),
        _Result(scalar=None),
        _Result(scalar=None),
    )
    service = AuthService()
    service._utcnow = lambda: NOW

    response = await service.bootstrap_actor_context(session, _identity())

    user, workspace, membership = session.added
    assert isinstance(user, User)
    assert isinstance(workspace, Workspace)
    assert isinstance(membership, WorkspaceMember)
    assert workspace.slug == "new-user-personal"
    assert membership.role == "owner"
    assert membership.joined_at == NOW
    assert response.user.id == user.id
    assert response.workspace.id == workspace.id
    assert response.bootstrap_completed is True


@pytest.mark.asyncio
async def test_bootstrap_selects_requested_workspace_and_repairs_default_membership():
    user_id = uuid.uuid4()
    default_id = uuid.uuid4()
    requested_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="user@example.com",
        display_name="Updated User",
        auth_provider="identity_platform",
        auth_subject="subject-1",
        is_active=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    default_workspace = SimpleNamespace(
        id=default_id,
        name="Personal",
        slug="personal",
        owner_user_id=user_id,
        is_personal=True,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    default_membership = SimpleNamespace(
        workspace_id=default_id,
        user_id=user_id,
        role="viewer",
        invited_by_user_id=user_id,
        joined_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    requested_workspace = SimpleNamespace(
        id=requested_id,
        name="Team",
        slug="team",
        owner_user_id=uuid.uuid4(),
        is_personal=False,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    requested_membership = SimpleNamespace(
        workspace_id=requested_id,
        user_id=user_id,
        role="editor",
        invited_by_user_id=None,
        joined_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session = _Session(
        _Result(scalar=user),
        _Result(scalar=default_workspace),
        _Result(scalar=default_membership),
        _Result(scalar=requested_membership),
        _Result(scalar=requested_workspace),
    )
    service = AuthService()
    service._utcnow = lambda: NOW

    response = await service.bootstrap_actor_context(session, _identity(), requested_id)

    assert default_membership.role == "owner"
    assert default_membership.joined_at == NOW
    assert response.workspace.id == requested_id
    assert response.membership.role == "editor"


@pytest.mark.asyncio
async def test_bootstrap_falls_back_to_default_workspace_when_requested_workspace_is_stale():
    user_id = uuid.uuid4()
    default_id = uuid.uuid4()
    requested_id = uuid.uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="user@example.com",
        display_name="Updated User",
        auth_provider="identity_platform",
        auth_subject="subject-1",
        is_active=True,
        last_login_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    default_workspace = SimpleNamespace(
        id=default_id,
        name="Personal",
        slug="personal",
        owner_user_id=user_id,
        is_personal=True,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    default_membership = SimpleNamespace(
        workspace_id=default_id,
        user_id=user_id,
        role="owner",
        invited_by_user_id=user_id,
        joined_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    session = _Session(
        _Result(scalar=user),
        _Result(scalar=default_workspace),
        _Result(scalar=default_membership),
        _Result(scalar=None),
    )
    service = AuthService()
    service._utcnow = lambda: NOW

    response = await service.bootstrap_actor_context(session, _identity(), requested_id)

    assert response.workspace.id == default_id
    assert response.membership.role == "owner"


@pytest.mark.asyncio
async def test_workspace_resolution_rejects_missing_membership_and_archived_workspace():
    service = AuthService()
    with pytest.raises(WorkspaceAccessError, match="not available"):
        await service._resolve_workspace_membership(
            _Session(_Result(scalar=None)), uuid.uuid4(), uuid.uuid4()
        )

    membership = SimpleNamespace()
    with pytest.raises(WorkspaceAccessError, match="archived"):
        await service._resolve_workspace_membership(
            _Session(_Result(scalar=membership), _Result(scalar=None)),
            uuid.uuid4(),
            uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_workspace_slug_collision_uses_stable_user_suffix():
    user = SimpleNamespace(id=uuid.UUID("12345678-1234-5678-1234-567812345678"), display_name="Jane Doe", email="jane@example.com")
    slug = await AuthService()._build_unique_workspace_slug(
        _Session(_Result(scalar=uuid.uuid4())), user
    )
    assert slug == "jane-doe-personal-12345678"


@pytest.mark.asyncio
async def test_workspace_context_and_member_lists_preserve_query_order():
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    workspace = SimpleNamespace(
        id=workspace_id,
        name="Personal",
        slug="personal",
        owner_user_id=user_id,
        is_personal=True,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    membership = SimpleNamespace(
        workspace_id=workspace_id,
        user_id=user_id,
        role="owner",
        invited_by_user_id=None,
        joined_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    service = AuthService()
    contexts = await service.list_workspace_contexts(
        _Session(_Result(rows=[(workspace, membership)])), user_id
    )
    members = await service.list_workspace_members(
        _Session(
            _Result(
                rows=[
                    (SimpleNamespace(id=user_id, display_name="Jane", email="jane@example.com"), membership),
                    (
                        SimpleNamespace(id=uuid.uuid4(), display_name="Zed", email="zed@example.com"),
                        SimpleNamespace(role="viewer"),
                    ),
                ]
            )
        ),
        workspace_id,
    )

    assert [item.workspace.slug for item in contexts.items] == ["personal"]
    assert [(item.display_name, item.role) for item in members.items] == [
        ("Jane", "owner"),
        ("Zed", "viewer"),
    ]

