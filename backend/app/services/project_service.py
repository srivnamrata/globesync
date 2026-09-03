from __future__ import annotations

import uuid
import hashlib
import json
import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectDraft, ProjectVersion
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
    ProjectVersionListResponse,
    ProjectVersionSummaryResponse,
    ProjectVersionResponse,
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
        cursor_updated_at, cursor_project_id = self._decode_project_cursor(query_params.cursor)
        stmt: Select[tuple[Project]] = (
            select(Project)
            .options(
                selectinload(Project.draft),
                selectinload(Project.media_file),
                selectinload(Project.current_lipsync_job),
                selectinload(Project.current_export_job),
            )
            .where(Project.workspace_id == workspace_id)
            .order_by(Project.updated_at.desc(), Project.id.desc())
            .limit(query_params.limit + 1)
        )

        if cursor_updated_at is not None and cursor_project_id is not None:
            stmt = stmt.where(
                or_(
                    Project.updated_at < cursor_updated_at,
                    and_(
                        Project.updated_at == cursor_updated_at,
                        Project.id < cursor_project_id,
                    ),
                )
            )

        if query_params.status:
            stmt = stmt.where(Project.status == query_params.status)
        if not query_params.include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))

        result = await db.execute(stmt)
        projects = list(result.scalars().all())
        has_next_page = len(projects) > query_params.limit
        page = projects[:query_params.limit]
        next_cursor = self._encode_project_cursor(page[-1]) if has_next_page and page else None
        return ProjectListResponse(
            items=[self._build_project_summary(project) for project in page],
            next_cursor=next_cursor,
        )

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
            merged_payload = self._merge_project_metadata(project, payload.draft_payload)
            draft = ProjectDraft(
                id=uuid.uuid4(),
                project_id=project.id,
                workspace_id=workspace_id,
                version=1,
                draft_schema_version=payload.draft_schema_version,
                draft_payload=merged_payload,
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
            merged_payload = self._merge_project_metadata(project, payload.draft_payload)
            draft.draft_payload = merged_payload
            draft.base_project_updated_at = payload.base_project_updated_at
            draft.last_saved_by_user_id = actor_user_id
            draft.updated_at = now

        project.updated_at = now
        await db.flush()
        await db.refresh(draft)
        if payload.checkpoint_reason:
            payload_hash = self._hash_payload(draft.draft_payload)
            latest_version = await db.scalar(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project.id)
                .order_by(ProjectVersion.version.desc())
                .limit(1)
            )
            if latest_version is None or not self._checkpoint_matches(
                latest_version,
                payload_hash,
                draft.draft_payload,
            ):
                db.add(ProjectVersion(
                    project_id=project.id,
                    workspace_id=workspace_id,
                    version=draft.version,
                    draft_schema_version=draft.draft_schema_version,
                    draft_payload=draft.draft_payload,
                    payload_hash=payload_hash,
                    checkpoint_reason=payload.checkpoint_reason,
                    created_by_user_id=actor_user_id,
                    created_at=now,
                ))

                version_ids = await db.scalars(
                    select(ProjectVersion.id)
                    .where(ProjectVersion.project_id == project.id)
                    .order_by(ProjectVersion.version.desc())
                    .offset(50)
                )
                stale_ids = list(version_ids)
                if stale_ids:
                    await db.execute(ProjectVersion.__table__.delete().where(ProjectVersion.id.in_(stale_ids)))

        return ProjectDraftPutResponse(
            project_id=draft.project_id,
            workspace_id=draft.workspace_id,
            version=draft.version,
            draft_schema_version=draft.draft_schema_version,
            base_project_updated_at=draft.base_project_updated_at,
            last_saved_by_user_id=draft.last_saved_by_user_id,
            updated_at=draft.updated_at,
        )

    async def list_project_versions(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ProjectVersionListResponse:
        await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        result = await db.execute(
            select(ProjectVersion)
            .where(
                ProjectVersion.project_id == project_id,
                ProjectVersion.workspace_id == workspace_id,
            )
            .order_by(ProjectVersion.version.desc())
        )
        return ProjectVersionListResponse(items=[
            ProjectVersionSummaryResponse(
                version=version.version,
                draft_schema_version=version.draft_schema_version,
                created_by_user_id=version.created_by_user_id,
                created_at=version.created_at,
            )
            for version in result.scalars().all()
        ])

    async def get_project_version(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        version_number: int,
        actor_user_id: uuid.UUID,
    ) -> ProjectVersionResponse:
        await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        version = await db.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project_id,
                ProjectVersion.workspace_id == workspace_id,
                ProjectVersion.version == version_number,
            )
        )
        if version is None:
            raise ProjectNotFoundError("Project version not found.")
        return ProjectVersionResponse(
            version=version.version,
            draft_schema_version=version.draft_schema_version,
            draft_payload=version.draft_payload,
            created_by_user_id=version.created_by_user_id,
            created_at=version.created_at,
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

    async def duplicate_project(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> ProjectDetailResponse:
        project = await self._get_scoped_project(db, workspace_id, project_id, actor_user_id)
        duplicate = Project(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            owner_user_id=actor_user_id,
            created_by_user_id=actor_user_id,
            name=f"{project.name} copy",
            status="draft",
            source_language=project.source_language,
            target_language=project.target_language,
            active_translation_language=project.active_translation_language,
        )
        db.add(duplicate)
        await db.flush()
        await db.refresh(duplicate)
        return self._build_project_detail(duplicate)

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

    def _build_project_summary(self, project: Project) -> ProjectSummaryResponse:
        latest_draft_version = self._loaded_draft_version(project)
        media = project.media_file
        export_job = project.current_export_job
        lipsync_job = project.current_lipsync_job
        pipeline_stage: str | None = None
        pipeline_status: str | None = None
        pipeline_progress_percent: int | None = None
        pipeline_error_message: str | None = None

        if export_job is not None:
            pipeline_stage = f"Export: {export_job.current_stage.replace('_', ' ')}"
            pipeline_status = export_job.status
            pipeline_progress_percent = int(export_job.progress_percent)
            pipeline_error_message = export_job.error_message
        elif lipsync_job is not None:
            pipeline_stage = "Lip-sync"
            pipeline_status = lipsync_job.status
            pipeline_progress_percent = int(lipsync_job.progress_percent)
            pipeline_error_message = lipsync_job.error_message

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
            media_filename=media.original_filename if media else None,
            media_duration_seconds=float(media.duration_seconds) if media else None,
            pipeline_stage=pipeline_stage,
            pipeline_status=pipeline_status,
            pipeline_progress_percent=pipeline_progress_percent,
            pipeline_error_message=pipeline_error_message,
            transcript_id=project.transcript_id,
            latest_draft_version=latest_draft_version,
            last_rendered_video_gcs_path=project.last_rendered_video_gcs_path,
            last_opened_at=project.last_opened_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def _build_project_detail(self, project: Project) -> ProjectDetailResponse:
        latest_draft_version = self._loaded_draft_version(project)
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

    @staticmethod
    def _hash_payload(payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _checkpoint_matches(version: ProjectVersion, payload_hash: str, payload: Dict[str, Any]) -> bool:
        return version.payload_hash == payload_hash or version.draft_payload == payload

    @staticmethod
    def _encode_project_cursor(project: Project) -> str:
        value = f"{project.updated_at.isoformat()}|{project.id}"
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_project_cursor(cursor: Optional[str]) -> tuple[datetime | None, uuid.UUID | None]:
        if not cursor:
            return None, None
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            updated_at, project_id = base64.urlsafe_b64decode(padded).decode("utf-8").split("|", 1)
            return datetime.fromisoformat(updated_at), uuid.UUID(project_id)
        except (ValueError, UnicodeDecodeError, base64.binascii.Error) as exc:
            raise ValueError("Invalid project cursor.") from exc


project_service = ProjectService()
