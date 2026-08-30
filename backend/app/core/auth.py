from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.schemas.auth import AuthBootstrapResponse, WorkspaceRole
from app.services.auth_service import WorkspaceAccessError, ResolvedIdentity, auth_service


WRITE_WORKSPACE_ROLES: tuple[WorkspaceRole, ...] = ("owner", "editor")


@dataclass(slots=True)
class AuthenticatedRequestContext:
    bootstrap: AuthBootstrapResponse
    auth_provider: str

    @property
    def user_id(self):
        return self.bootstrap.user.id

    @property
    def workspace_id(self):
        return self.bootstrap.workspace.id

    @property
    def membership_role(self):
        return self.bootstrap.membership.role


async def get_request_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedRequestContext:
    identity = await _resolve_identity(request)
    requested_workspace_id = _parse_workspace_override(request)

    try:
        bootstrap = await auth_service.bootstrap_actor_context(
            db=db,
            identity=identity,
            requested_workspace_id=requested_workspace_id,
        )
    except WorkspaceAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return AuthenticatedRequestContext(
        bootstrap=bootstrap,
        auth_provider=identity.auth_provider,
    )


async def require_workspace_write_context(
    context: AuthenticatedRequestContext = Depends(get_request_context),
) -> AuthenticatedRequestContext:
    _ensure_workspace_write_role(context)
    return context


async def get_scoped_project(
    project_id: uuid.UUID,
    db: AsyncSession,
    context: AuthenticatedRequestContext,
    *,
    require_write: bool = False,
    not_found_detail: str = "Project not found.",
) -> Project:
    if require_write:
        _ensure_workspace_write_role(context)

    stmt = select(Project).where(
        Project.id == project_id,
        Project.workspace_id == context.workspace_id,
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    return project


async def ensure_workspace_resource_access(
    *,
    db: AsyncSession,
    context: AuthenticatedRequestContext,
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    require_write: bool = False,
    not_found_detail: str = "Resource not found.",
) -> None:
    if require_write:
        _ensure_workspace_write_role(context)

    if workspace_id is not None:
        if workspace_id != context.workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
        return

    if project_id is not None:
        await get_scoped_project(
            project_id=project_id,
            db=db,
            context=context,
            require_write=False,
            not_found_detail=not_found_detail,
        )
        return

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)


def _ensure_workspace_write_role(context: AuthenticatedRequestContext) -> None:
    if context.membership_role not in WRITE_WORKSPACE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace membership role does not allow this operation.",
        )


async def _resolve_identity(request: Request) -> ResolvedIdentity:
    debug_identity = _resolve_debug_identity(request)
    if debug_identity is not None:
        return debug_identity

    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    claims = await _verify_google_identity_token(token)
    email = str(claims.get("email") or "").strip().lower()
    subject = str(claims.get("sub") or "").strip()
    display_name = str(claims.get("name") or "").strip() or None
    email_verified = bool(claims.get("email_verified", False))

    if not email or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity token is missing required subject or email claims.",
        )
    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity token email must be verified.",
        )

    return ResolvedIdentity(
        email=email,
        display_name=display_name,
        auth_subject=subject,
        auth_provider=settings.AUTH_PROVIDER,
        email_verified=email_verified,
    )


def _resolve_debug_identity(request: Request) -> ResolvedIdentity | None:
    if not settings.ALLOW_INSECURE_DEV_AUTH:
        return None

    email = (request.headers.get("X-Debug-User-Email") or "").strip().lower()
    if not email:
        return None

    subject = (request.headers.get("X-Debug-User-Subject") or email).strip()
    display_name = (request.headers.get("X-Debug-User-Name") or email.split("@", 1)[0]).strip()
    return ResolvedIdentity(
        email=email,
        display_name=display_name or None,
        auth_subject=subject,
        auth_provider="debug",
        email_verified=True,
    )


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _verify_google_identity_token(token: str) -> dict:
    audiences = [client_id.strip() for client_id in settings.GOOGLE_OAUTH_CLIENT_IDS if client_id.strip()]

    def _verify() -> dict:
        google_request = GoogleAuthRequest()
        if len(audiences) == 1:
            return id_token.verify_oauth2_token(token, google_request, audiences[0])
        return id_token.verify_oauth2_token(token, google_request)

    try:
        claims = await asyncio.to_thread(_verify)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify identity token.",
        ) from exc

    if audiences:
        token_audience = str(claims.get("aud") or "").strip()
        if token_audience not in audiences:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identity token audience is not allowed.",
            )

    return claims


def _parse_workspace_override(request: Request) -> uuid.UUID | None:
    workspace_header = (request.headers.get("X-Workspace-Id") or "").strip()
    if not workspace_header:
        return None

    try:
        return uuid.UUID(workspace_header)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Workspace-Id must be a valid UUID.",
        ) from exc
