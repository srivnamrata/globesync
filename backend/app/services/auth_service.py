from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User, Workspace, WorkspaceMember
from app.schemas.auth import (
    AuthBootstrapResponse,
    AuthenticatedUserResponse,
    WorkspaceMembershipResponse,
    WorkspaceContextResponse,
    WorkspaceListResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberResponse,
    WorkspaceSummaryResponse,
)


class AuthServiceError(Exception):
    """Base service error for auth bootstrap operations."""


class WorkspaceAccessError(AuthServiceError):
    """Raised when a user requests a workspace they do not belong to."""


@dataclass(slots=True)
class ResolvedIdentity:
    email: str
    display_name: Optional[str]
    auth_subject: Optional[str]
    auth_provider: str = "identity_platform"
    email_verified: bool = True


class AuthService:
    """Bootstraps persisted actor and workspace context from verified identity claims."""

    async def bootstrap_actor_context(
        self,
        db: AsyncSession,
        identity: ResolvedIdentity,
        requested_workspace_id: uuid.UUID | None = None,
    ) -> AuthBootstrapResponse:
        user = await self._get_or_create_user(db, identity)
        workspace, membership = await self._get_or_create_default_workspace(db, user)

        if requested_workspace_id is not None and requested_workspace_id != workspace.id:
            workspace, membership = await self._resolve_workspace_membership(db, user.id, requested_workspace_id)

        await db.flush()
        return self._build_bootstrap_response(user, workspace, membership)

    async def list_workspace_contexts(self, db: AsyncSession, user_id: uuid.UUID) -> WorkspaceListResponse:
        result = await db.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                WorkspaceMember.user_id == user_id,
                Workspace.archived_at.is_(None),
            )
            .order_by(Workspace.is_personal.desc(), Workspace.name.asc())
        )
        items = []
        for workspace, membership in result.all():
            items.append(
                WorkspaceContextResponse(
                    workspace=WorkspaceSummaryResponse(
                        id=workspace.id,
                        name=workspace.name,
                        slug=workspace.slug,
                        owner_user_id=workspace.owner_user_id,
                        is_personal=workspace.is_personal,
                        archived_at=workspace.archived_at,
                        created_at=workspace.created_at,
                        updated_at=workspace.updated_at,
                    ),
                    membership=WorkspaceMembershipResponse(
                        workspace_id=membership.workspace_id,
                        user_id=membership.user_id,
                        role=membership.role,
                        invited_by_user_id=membership.invited_by_user_id,
                        joined_at=membership.joined_at,
                        created_at=membership.created_at,
                        updated_at=membership.updated_at,
                    ),
                )
            )
        return WorkspaceListResponse(items=items)

    async def list_workspace_members(self, db: AsyncSession, workspace_id: uuid.UUID) -> WorkspaceMemberListResponse:
        result = await db.execute(
            select(User, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.role.asc(), User.display_name.asc(), User.email.asc())
        )
        return WorkspaceMemberListResponse(
            items=[
                WorkspaceMemberResponse(
                    user_id=user.id,
                    display_name=user.display_name,
                    email=user.email,
                    role=membership.role,
                )
                for user, membership in result.all()
            ]
        )

    async def _get_or_create_user(self, db: AsyncSession, identity: ResolvedIdentity) -> User:
        stmt: Select[tuple[User]]
        user: User | None = None

        if identity.auth_subject:
            stmt = select(User).where(
                User.auth_provider == identity.auth_provider,
                User.auth_subject == identity.auth_subject,
            )
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

        if user is None:
            stmt = select(User).where(User.email == identity.email)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

        now = self._utcnow()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email=identity.email,
                display_name=identity.display_name,
                auth_provider=identity.auth_provider,
                auth_subject=identity.auth_subject,
                is_active=True,
                last_login_at=now,
            )
            db.add(user)
            await db.flush()
            return user

        user.email = identity.email
        if identity.display_name:
            user.display_name = identity.display_name
        if identity.auth_subject and not user.auth_subject:
            user.auth_subject = identity.auth_subject
        if not user.is_active:
            user.is_active = True
        user.last_login_at = now
        user.updated_at = now
        await db.flush()
        return user

    async def _get_or_create_default_workspace(
        self,
        db: AsyncSession,
        user: User,
    ) -> tuple[Workspace, WorkspaceMember]:
        stmt = select(Workspace).where(
            Workspace.owner_user_id == user.id,
            Workspace.is_personal.is_(True),
            Workspace.archived_at.is_(None),
        )
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if workspace is None:
            workspace = Workspace(
                id=uuid.uuid4(),
                name=self._build_personal_workspace_name(user),
                slug=await self._build_unique_workspace_slug(db, user),
                owner_user_id=user.id,
                is_personal=True,
            )
            db.add(workspace)
            await db.flush()

        membership = await self._ensure_membership(db, workspace.id, user.id, role="owner", invited_by_user_id=user.id)
        return workspace, membership

    async def _resolve_workspace_membership(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> tuple[Workspace, WorkspaceMember]:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        membership = result.scalar_one_or_none()
        if membership is None:
            raise WorkspaceAccessError("Requested workspace is not available to the current actor.")

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.archived_at.is_(None))
        )
        workspace = workspace_result.scalar_one_or_none()
        if workspace is None:
            raise WorkspaceAccessError("Requested workspace is archived or does not exist.")

        return workspace, membership

    async def _ensure_membership(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        invited_by_user_id: uuid.UUID | None,
    ) -> WorkspaceMember:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        membership = result.scalar_one_or_none()
        now = self._utcnow()

        if membership is None:
            membership = WorkspaceMember(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                invited_by_user_id=invited_by_user_id,
                joined_at=now,
            )
            db.add(membership)
            await db.flush()
            return membership

        membership.role = role
        if membership.joined_at is None:
            membership.joined_at = now
        membership.updated_at = now
        await db.flush()
        return membership

    async def _build_unique_workspace_slug(self, db: AsyncSession, user: User) -> str:
        base_slug = self._slugify(user.display_name or user.email.split("@", 1)[0]) or "workspace"
        candidate = f"{base_slug}-personal"

        result = await db.execute(select(Workspace.id).where(Workspace.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate

        return f"{candidate}-{str(user.id)[:8]}"

    def _build_personal_workspace_name(self, user: User) -> str:
        display = (user.display_name or user.email.split("@", 1)[0]).strip()
        return f"{display} Personal Workspace"

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug[:96]

    def _build_bootstrap_response(
        self,
        user: User,
        workspace: Workspace,
        membership: WorkspaceMember,
    ) -> AuthBootstrapResponse:
        return AuthBootstrapResponse(
            user=AuthenticatedUserResponse(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                auth_provider=user.auth_provider,
                auth_subject=user.auth_subject,
                is_active=user.is_active,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                updated_at=user.updated_at,
            ),
            workspace=WorkspaceSummaryResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                owner_user_id=workspace.owner_user_id,
                is_personal=workspace.is_personal,
                archived_at=workspace.archived_at,
                created_at=workspace.created_at,
                updated_at=workspace.updated_at,
            ),
            membership=WorkspaceMembershipResponse(
                workspace_id=membership.workspace_id,
                user_id=membership.user_id,
                role=membership.role,
                invited_by_user_id=membership.invited_by_user_id,
                joined_at=membership.joined_at,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            ),
            bootstrap_completed=True,
        )

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


auth_service = AuthService()
