from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedRequestContext, get_request_context
from app.core.database import get_db
from app.schemas.auth import AuthBootstrapResponse, WorkspaceListResponse, WorkspaceMemberListResponse
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/bootstrap",
    response_model=AuthBootstrapResponse,
    summary="Bootstrap Authenticated User Context",
)
async def bootstrap_authenticated_context(
    context: AuthenticatedRequestContext = Depends(get_request_context),
):
    return context.bootstrap


@router.get(
    "/me",
    response_model=AuthBootstrapResponse,
    summary="Get Current Authenticated Context",
)
async def get_authenticated_context(
    context: AuthenticatedRequestContext = Depends(get_request_context),
):
    return context.bootstrap


@router.get(
    "/workspaces",
    response_model=WorkspaceListResponse,
    summary="List Available Workspaces",
)
async def list_available_workspaces(
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.list_workspace_contexts(db=db, user_id=context.user_id)


@router.get(
    "/workspace-members",
    response_model=WorkspaceMemberListResponse,
    summary="List Current Workspace Members",
)
async def list_current_workspace_members(
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    return await auth_service.list_workspace_members(db=db, workspace_id=context.workspace_id)
