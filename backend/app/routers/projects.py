import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    AuthenticatedRequestContext,
    get_request_context,
    require_workspace_write_context,
)
from app.core.database import get_db
from app.schemas.projects import (
    DraftConflictErrorResponse,
    ProjectArchiveResponse,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectDraftPutRequest,
    ProjectDraftPutResponse,
    ProjectDraftResponse,
    ProjectListQueryParams,
    ProjectListResponse,
    ProjectUpdateRequest,
)
from app.services.project_service import (
    ProjectDraftConflictError,
    ProjectNotFoundError,
    project_service,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List Projects",
)
async def list_projects(
    status_filter: str | None = Query(None, alias="status", description="Optional project status filter"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    include_archived: bool = Query(False),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    filters = ProjectListQueryParams(
        status=status_filter,
        limit=limit,
        cursor=cursor,
        include_archived=include_archived,
    )
    return await project_service.list_projects(
        db=db,
        workspace_id=context.workspace_id,
        filters=filters,
        actor_user_id=context.user_id,
    )


@router.post(
    "",
    response_model=ProjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project",
)
async def create_project(
    req: ProjectCreateRequest,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.create_project(
        db=db,
        workspace_id=context.workspace_id,
        payload=req,
        actor_user_id=context.user_id,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get Project",
)
async def get_project(
    project_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_service.get_project(
            db=db,
            workspace_id=context.workspace_id,
            project_id=project_id,
            actor_user_id=context.user_id,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Update Project",
)
async def update_project(
    req: ProjectUpdateRequest,
    project_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_service.update_project(
            db=db,
            workspace_id=context.workspace_id,
            project_id=project_id,
            payload=req,
            actor_user_id=context.user_id,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/draft",
    response_model=ProjectDraftResponse,
    summary="Get Project Draft",
)
async def get_project_draft(
    project_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_service.get_project_draft(
            db=db,
            workspace_id=context.workspace_id,
            project_id=project_id,
            actor_user_id=context.user_id,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/{project_id}/draft",
    response_model=ProjectDraftPutResponse,
    responses={409: {"model": DraftConflictErrorResponse}},
    summary="Save Project Draft",
)
async def put_project_draft(
    req: ProjectDraftPutRequest,
    project_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_service.put_project_draft(
            db=db,
            workspace_id=context.workspace_id,
            project_id=project_id,
            payload=req,
            actor_user_id=context.user_id,
        )
    except ProjectDraftConflictError as exc:
        return JSONResponse(status_code=409, content={"error": exc.detail.model_dump(mode="json")})
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{project_id}/archive",
    response_model=ProjectArchiveResponse,
    summary="Archive Project",
)
async def archive_project(
    project_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await project_service.archive_project(
            db=db,
            workspace_id=context.workspace_id,
            project_id=project_id,
            actor_user_id=context.user_id,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
