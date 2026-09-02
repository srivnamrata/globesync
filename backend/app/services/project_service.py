from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectDraft
from app.schemas.projects import (
    DraftConflictErrorDetail,
    ProjectArchiveResponse,
    ProjectCreateRequest,
    ProjectDetailResponse,
    ProjectDraftPutRequest,
    ProjectDraftPutResponse,
    ProjectDraftResponse,
    ProjectListQueryParams,
    ProjectListResponse,
    ProjectSummaryResponse,
    ProjectUpdateRequest,
)
from app.services.storage_service import storage_service


class ProjectServiceError(Exception):
    """Base service error for project operations."""


class ProjectNotFoundError(ProjectServiceError):
    """Raised when a project is not found in the expected workspace scope."""


class ProjectDraftConflictError(ProjectServiceError):
    """Raised when a draft write uses a stale version."""

    def __init__(self, detail: DraftConflictErrorDetail):
        super().__init__(detail.message)
        self.detail = detail


class ProjectAuthorizationError(ProjectServiceError):
    """Raised when the current actor is not allowed to modify a project."""


class ProjectService:
    """Workspace-scoped CRUD and draft persistence helpers for projects."""

    async def list_projects(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        filters: Optional[ProjectListQueryParams] = None,
    ) -> ProjectListResponse:
        query_params = filters or ProjectListQueryParams()
        stmt: Select[tuple[Project]] = (
            select(Project)
            .options(selectinload(Project.draft), selectinload(Project.media_file))
            .where(Project.workspace_id == workspace_id)
            .order_by(Project.updated_at.desc())
            .limit(query_params.limit)
        )

        if query_params.status:
            stmt = stmt.where(Project.status == query_params.status)
        if not query_params.include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))

        result = await db.execute(stmt)
        projects = result.scalars().all()
        return ProjectListResponse(items=[self._build_project_summary(project) for project in projects])

    async def create_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        payload: ProjectCreateRequest,
        actor_user_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        project = Project(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            owner_user_id=actor_user_id,
            created_by_user_id=actor_user_id,
            name=payload.name,
            status="draft",
            source_language=payload.source_language,
            target_language=payload.target_language,
            active_translation_language=payload.target_language,
        )
        db.add(project)
        await db.flush()
        await db.refresh(project)
        return self._build_project_detail(project)

    async def get_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        return self._build_project_detail(project)

    async def update_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        payload: ProjectUpdateRequest,
        actor_user_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)

        if payload.name is not None:
            project.name = payload.name
        if payload.status is not None:
            project.status = payload.status
            if payload.status == "archived" and project.archived_at is None:
                project.archived_at = self._utcnow()
            elif payload.status != "archived":
                project.archived_at = None
        if payload.source_language is not None:
            project.source_language = payload.source_language
        if payload.target_language is not None:
            project.target_language = payload.target_language
        if payload.active_translation_language is not None:
            project.active_translation_language = payload.active_translation_language
        if payload.media_file_id is not None:
            project.media_file_id = payload.media_file_id
        if payload.transcript_id is not None:
            project.transcript_id = payload.transcript_id
        if payload.current_lipsync_job_id is not None:
            project.current_lipsync_job_id = payload.current_lipsync_job_id
        if payload.current_export_job_id is not None:
            project.current_export_job_id = payload.current_export_job_id
        if payload.last_rendered_video_gcs_path is not None:
            project.last_rendered_video_gcs_path = payload.last_rendered_video_gcs_path

        project.updated_at = self._utcnow()
        await db.flush()
        await db.refresh(project)
        return self._build_project_detail(project)

    async def get_project_draft(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ProjectDraftResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        draft = project.draft
        if not draft:
            raise ProjectNotFoundError("Project draft not found.")
        return self._build_project_draft_response(project, draft)

    async def put_project_draft(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        payload: ProjectDraftPutRequest,
        actor_user_id: uuid.UUID,
    ) -> ProjectDraftPutResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        draft = project.draft
        now = self._utcnow()

        if draft is None:
            if payload.version != 1:
                raise ProjectDraftConflictError(
                    DraftConflictErrorDetail(
                        project_id=project_id,
                        client_version=payload.version,
                        server_version=0,
                        server_updated_at=project.updated_at,
                        last_saved_by_user_id=project.created_by_user_id,
                    )
                )
            draft = ProjectDraft(
                id=uuid.uuid4(),
                project_id=project.id,
                workspace_id=workspace_id,
                version=1,
                draft_schema_version=payload.draft_schema_version,
                draft_payload=self._merge_project_metadata(project, payload.draft_payload),
                base_project_updated_at=payload.base_project_updated_at,
                last_saved_by_user_id=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(draft)
        else:
            if payload.version != draft.version:
                raise ProjectDraftConflictError(
                    DraftConflictErrorDetail(
                        project_id=project_id,
                        client_version=payload.version,
                        server_version=draft.version,
                        server_updated_at=draft.updated_at,
                        last_saved_by_user_id=draft.last_saved_by_user_id,
                    )
                )
            draft.version += 1
            draft.draft_schema_version = payload.draft_schema_version
            draft.draft_payload = self._merge_project_metadata(project, payload.draft_payload)
            draft.base_project_updated_at = payload.base_project_updated_at
            draft.last_saved_by_user_id = actor_user_id
            draft.updated_at = now

        project.updated_at = now
        await db.flush()
        await db.refresh(draft)

        return ProjectDraftPutResponse(
            project_id=draft.project_id,
            workspace_id=draft.workspace_id,
            version=draft.version,
            draft_schema_version=draft.draft_schema_version,
            base_project_updated_at=draft.base_project_updated_at,
            last_saved_by_user_id=draft.last_saved_by_user_id,
            updated_at=draft.updated_at,
        )

    async def archive_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ProjectArchiveResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        now = self._utcnow()
        project.status = "archived"
        project.archived_at = now
        project.updated_at = now
        await db.flush()
        await db.refresh(project)
        return ProjectArchiveResponse(
            id=project.id,
            workspace_id=project.workspace_id,
            status=project.status,
            archived_at=project.archived_at,
            updated_at=project.updated_at,
        )

    async def _get_scoped_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> Project:
        stmt = (
            select(Project)
            .options(selectinload(Project.draft), selectinload(Project.media_file))
            .where(
                Project.id == project_id,
                Project.workspace_id == workspace_id,
            )
        )

        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise ProjectNotFoundError("Project not found.")
        return project

    def _loaded_draft_version(self, project: Project) -> int:
        draft = project.__dict__.get("draft")
        return draft.version if draft else 0

    def _build_rendered_video_url(self, project: Project) -> Optional[str]:
        if not project.last_rendered_video_gcs_path:
            return None
        return storage_service.generate_presigned_download_url(
            project.last_rendered_video_gcs_path,
            expires_in_seconds=7200,
        )

    def _build_project_summary(self, project: Project) -> ProjectSummaryResponse:
        latest_draft_version = self._loaded_draft_version(project)
        rendered_video_url = self._build_rendered_video_url(project)
        return ProjectSummaryResponse(
            id=project.id,
            workspace_id=project.workspace_id,
            owner_user_id=project.owner_user_id,
            name=project.name,
            status=project.status,
            source_language=project.source_language,
            target_language=project.target_language,
            active_translation_language=project.active_translation_language,
            media_file_id=project.media_file_id,
            transcript_id=project.transcript_id,
            latest_draft_version=latest_draft_version,
            last_rendered_video_gcs_path=project.last_rendered_video_gcs_path,
            last_rendered_video_url=rendered_video_url,
            last_opened_at=project.last_opened_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _build_project_detail(self, project: Project) -> ProjectDetailResponse:
        latest_draft_version = self._loaded_draft_version(project)
        rendered_video_url = self._build_rendered_video_url(project)
        return ProjectDetailResponse(
            id=project.id,
            workspace_id=project.workspace_id,
            owner_user_id=project.owner_user_id,
            created_by_user_id=project.created_by_user_id,
            name=project.name,
            slug=project.slug,
            status=project.status,
            source_language=project.source_language,
            target_language=project.target_language,
            active_translation_language=project.active_translation_language,
            media_file_id=project.media_file_id,
            transcript_id=project.transcript_id,
            current_lipsync_job_id=project.current_lipsync_job_id,
            current_export_job_id=project.current_export_job_id,
            last_rendered_video_gcs_path=project.last_rendered_video_gcs_path,
            last_rendered_video_url=rendered_video_url,
            latest_draft_version=latest_draft_version,
            archived_at=project.archived_at,
            last_opened_at=project.last_opened_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _build_project_draft_response(self, project: Project, draft: ProjectDraft) -> ProjectDraftResponse:
        return ProjectDraftResponse(
            project_id=draft.project_id,
            workspace_id=draft.workspace_id,
            version=draft.version,
            draft_schema_version=draft.draft_schema_version,
            base_project_updated_at=draft.base_project_updated_at,
            last_saved_by_user_id=draft.last_saved_by_user_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            draft_payload=self._merge_project_metadata(project, draft.draft_payload or {}),
        )

    def _merge_project_metadata(self, project: Project, draft_payload: Dict[str, Any]) -> Dict[str, Any]:
        merged_payload = dict(draft_payload)
        project_metadata = dict(merged_payload.get("projectMetadata") or {})
        project_metadata.setdefault("id", str(project.id))
        project_metadata["name"] = project.name
        project_metadata["sourceLanguage"] = project.source_language
        project_metadata["targetLanguage"] = project.target_language
        project_metadata["status"] = project.status
        project_metadata["createdAt"] = project.created_at.isoformat()
        project_metadata["updatedAt"] = project.updated_at.isoformat()
        merged_payload["projectMetadata"] = project_metadata

        media_references = dict(merged_payload.get("mediaReferences") or {})
        if project.media_file_id is not None:
            media_references["mediaId"] = str(project.media_file_id)
        if project.transcript_id is not None:
            media_references["transcriptId"] = str(project.transcript_id)
        if project.media_file is not None:
            media_references["videoFilename"] = project.media_file.original_filename
            media_references["durationSeconds"] = float(project.media_file.duration_seconds)
        merged_payload["mediaReferences"] = media_references
        return merged_payload

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)


project_service = ProjectService()
