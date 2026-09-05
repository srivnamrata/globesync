from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy import JSON, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.models.media import MediaFile
from app.models.project import Project, ProjectDraft, ProjectVersion
from app.services.project_service import ProjectDraftConflictError, ProjectNotFoundError, ProjectService
from app.schemas.projects import ProjectDraftPutRequest


class SQLiteUUID(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(str(value)).hex

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(str(value))


WORKSPACE_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
WORKSPACE_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OWNER_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OTHER_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
PROJECT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
SECOND_PROJECT_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
TRANSCRIPT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")

FIXED_CREATED_AT = datetime(2026, 9, 3, 12, 0, 0)
FIXED_UPDATED_AT = datetime(2026, 9, 3, 13, 0, 0)
FIXED_SAVE_AT = datetime(2026, 9, 3, 14, 0, 0)


def _patch_sqlite_types():
    saved_types = []
    for table in (MediaFile.__table__, Project.__table__, ProjectDraft.__table__, ProjectVersion.__table__):
        for column in table.columns:
            if isinstance(column.type, PGUUID):
                saved_types.append((column, column.type))
                column.type = SQLiteUUID()

    for column in (
        MediaFile.__table__.columns["raw_probe_metadata"],
        ProjectDraft.__table__.columns["draft_payload"],
        ProjectVersion.__table__.columns["draft_payload"],
    ):
        saved_types.append((column, column.type))
        column.type = JSON()

    return saved_types


def _restore_sqlite_types(saved_types):
    for column, original_type in saved_types:
        column.type = original_type


@asynccontextmanager
async def _project_db():
    saved_types = _patch_sqlite_types()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: MediaFile.__table__.create(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: Project.__table__.create(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: ProjectDraft.__table__.create(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: ProjectVersion.__table__.create(sync_conn, checkfirst=True))

        session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        yield session_factory
    finally:
        await engine.dispose()
        _restore_sqlite_types(saved_types)


def _project_payload(*, editor_zoom: int, theme: str = "dark") -> dict:
    return {
        "version": "heygenx/v1",
        "editorState": {"theme": theme, "zoom": editor_zoom},
        "timelineState": {"playbackRate": 1, "zoomLevel": editor_zoom * 100},
    }


def _project_payload_reordered(*, editor_zoom: int, theme: str = "dark") -> dict:
    return {
        "timelineState": {"zoomLevel": editor_zoom * 100, "playbackRate": 1},
        "editorState": {"zoom": editor_zoom, "theme": theme},
        "version": "heygenx/v1",
    }


def _merged_payload(*, project_name: str, project_status: str, source_language: str, target_language: str, payload: dict) -> dict:
    merged = dict(payload)
    merged["projectMetadata"] = {
        "id": str(PROJECT_ID),
        "name": project_name,
        "sourceLanguage": source_language,
        "targetLanguage": target_language,
        "status": project_status,
        "createdAt": FIXED_CREATED_AT.isoformat(),
        "updatedAt": FIXED_UPDATED_AT.isoformat(),
    }
    merged["mediaReferences"] = {"transcriptId": str(TRANSCRIPT_ID)}
    return merged


async def _seed_project(
    db: AsyncSession,
    *,
    project_id: uuid.UUID = PROJECT_ID,
    workspace_id: uuid.UUID = WORKSPACE_A_ID,
    owner_user_id: uuid.UUID = OWNER_USER_ID,
    created_by_user_id: uuid.UUID = OWNER_USER_ID,
    name: str = "Demo project",
    status: str = "draft",
    source_language: str = "en",
    target_language: str = "es",
    active_translation_language: str = "es",
    transcript_id: uuid.UUID | None = TRANSCRIPT_ID,
    draft_version: int | None = None,
    draft_payload: dict | None = None,
    draft_saved_by_user_id: uuid.UUID | None = None,
    draft_updated_at: datetime = FIXED_UPDATED_AT,
    version_rows: list[ProjectVersion] | None = None,
) -> Project:
    project = Project(
        id=project_id,
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        created_by_user_id=created_by_user_id,
        name=name,
        status=status,
        source_language=source_language,
        target_language=target_language,
        active_translation_language=active_translation_language,
        transcript_id=transcript_id,
        created_at=FIXED_CREATED_AT,
        updated_at=FIXED_UPDATED_AT,
    )
    db.add(project)

    if draft_version is not None:
        db.add(
            ProjectDraft(
                id=uuid.uuid4(),
                project_id=project_id,
                workspace_id=workspace_id,
                version=draft_version,
                draft_schema_version="heygenx/v1",
                draft_payload=draft_payload or _merged_payload(
                    project_name=name,
                    project_status=status,
                    source_language=source_language,
                    target_language=target_language,
                    payload=_project_payload(editor_zoom=1),
                ),
                base_project_updated_at=FIXED_UPDATED_AT,
                last_saved_by_user_id=draft_saved_by_user_id or created_by_user_id,
                created_at=FIXED_CREATED_AT,
                updated_at=draft_updated_at,
            )
        )

    for version in version_rows or []:
        db.add(version)

    await db.commit()
    return project


def _make_version(
    *,
    version: int,
    project_id: uuid.UUID = PROJECT_ID,
    workspace_id: uuid.UUID = WORKSPACE_A_ID,
    created_by_user_id: uuid.UUID = OWNER_USER_ID,
    checkpoint_reason: str = "manual_save",
    payload: dict | None = None,
    created_at: datetime = FIXED_SAVE_AT,
) -> ProjectVersion:
    version_payload = payload or _merged_payload(
        project_name="Demo project",
        project_status="draft",
        source_language="en",
        target_language="es",
        payload=_project_payload(editor_zoom=1),
    )
    return ProjectVersion(
        id=uuid.uuid4(),
        project_id=project_id,
        workspace_id=workspace_id,
        version=version,
        draft_schema_version="heygenx/v1",
        draft_payload=version_payload,
        payload_hash=ProjectService._hash_payload(version_payload),
        checkpoint_reason=checkpoint_reason,
        created_by_user_id=created_by_user_id,
        created_at=created_at,
    )


def test_hash_payload_is_order_independent() -> None:
    first = {
        "translations": [{"id": "segment-1", "text": "Hello"}],
        "timelineState": {"zoomLevel": 100},
    }
    reordered = {
        "timelineState": {"zoomLevel": 100},
        "translations": [{"id": "segment-1", "text": "Hello"}],
    }

    assert ProjectService._hash_payload(first) == ProjectService._hash_payload(reordered)


@pytest.mark.asyncio
async def test_put_project_draft_creates_initial_snapshot_and_merges_metadata() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()
        service._utcnow = lambda: FIXED_SAVE_AT

        async with session_factory() as db:
            await _seed_project(
                db,
                name="Demo project",
                transcript_id=TRANSCRIPT_ID,
                draft_version=None,
            )

        async with session_factory() as db:
            response = await service.put_project_draft(
                db,
                WORKSPACE_A_ID,
                PROJECT_ID,
                ProjectDraftPutRequest(
                    version=1,
                    draft_schema_version="heygenx/v1",
                    base_project_updated_at=FIXED_UPDATED_AT,
                    draft_payload=_project_payload(editor_zoom=1),
                    checkpoint_reason="manual_save",
                ),
                OWNER_USER_ID,
            )
            await db.commit()

            assert response.project_id == PROJECT_ID
            assert response.workspace_id == WORKSPACE_A_ID
            assert response.version == 1
            assert response.base_project_updated_at == FIXED_UPDATED_AT
            assert response.last_saved_by_user_id == OWNER_USER_ID
            assert response.updated_at == FIXED_SAVE_AT

            draft_row = (
                await db.execute(select(ProjectDraft).where(ProjectDraft.project_id == PROJECT_ID))
            ).scalar_one()
            version_row = (
                await db.execute(select(ProjectVersion).where(ProjectVersion.project_id == PROJECT_ID))
            ).scalar_one()

            expected_payload = _merged_payload(
                project_name="Demo project",
                project_status="draft",
                source_language="en",
                target_language="es",
                payload=_project_payload(editor_zoom=1),
            )
            assert draft_row.version == 1
            assert draft_row.last_saved_by_user_id == OWNER_USER_ID
            assert draft_row.draft_payload == expected_payload
            assert version_row.version == 1
            assert version_row.checkpoint_reason == "manual_save"
            assert version_row.created_by_user_id == OWNER_USER_ID
            assert version_row.payload_hash == ProjectService._hash_payload(expected_payload)
            assert version_row.draft_payload == expected_payload


@pytest.mark.asyncio
async def test_put_project_draft_rejects_stale_create_version_conflict() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()

        async with session_factory() as db:
            await _seed_project(db, draft_version=None)

        async with session_factory() as db:
            with pytest.raises(ProjectDraftConflictError) as exc_info:
                await service.put_project_draft(
                    db,
                    WORKSPACE_A_ID,
                    PROJECT_ID,
                    ProjectDraftPutRequest(
                        version=2,
                        draft_schema_version="heygenx/v1",
                        base_project_updated_at=FIXED_UPDATED_AT,
                        draft_payload=_project_payload_reordered(editor_zoom=1),
                    ),
                    OTHER_USER_ID,
                )

            detail = exc_info.value.detail
            assert detail.client_version == 2
            assert detail.server_version == 0
            assert detail.server_updated_at == FIXED_UPDATED_AT
            assert detail.last_saved_by_user_id == OWNER_USER_ID

            draft_count = await db.scalar(select(ProjectDraft).where(ProjectDraft.project_id == PROJECT_ID))
            assert draft_count is None


@pytest.mark.asyncio
async def test_put_project_draft_rejects_stale_update_version_conflict() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()

        async with session_factory() as db:
            await _seed_project(
                db,
                draft_version=3,
                draft_payload=_merged_payload(
                    project_name="Demo project",
                    project_status="draft",
                    source_language="en",
                    target_language="es",
                    payload=_project_payload(editor_zoom=1),
                ),
                draft_saved_by_user_id=OTHER_USER_ID,
                draft_updated_at=FIXED_SAVE_AT,
            )

        async with session_factory() as db:
            with pytest.raises(ProjectDraftConflictError) as exc_info:
                await service.put_project_draft(
                    db,
                    WORKSPACE_A_ID,
                    PROJECT_ID,
                    ProjectDraftPutRequest(
                        version=2,
                        draft_schema_version="heygenx/v1",
                        base_project_updated_at=FIXED_SAVE_AT,
                        draft_payload=_project_payload_reordered(editor_zoom=2),
                        checkpoint_reason="manual_save",
                    ),
                    OWNER_USER_ID,
                )

            detail = exc_info.value.detail
            assert detail.client_version == 2
            assert detail.server_version == 3
            assert detail.server_updated_at == FIXED_SAVE_AT
            assert detail.last_saved_by_user_id == OTHER_USER_ID

            draft_row = (
                await db.execute(select(ProjectDraft).where(ProjectDraft.project_id == PROJECT_ID))
            ).scalar_one()
            assert draft_row.version == 3
            assert draft_row.last_saved_by_user_id == OTHER_USER_ID


@pytest.mark.asyncio
async def test_put_project_draft_allows_cross_user_save_and_dedupes_matching_checkpoint() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()
        service._utcnow = lambda: FIXED_SAVE_AT

        initial_payload = _merged_payload(
            project_name="Demo project",
            project_status="draft",
            source_language="en",
            target_language="es",
            payload=_project_payload(editor_zoom=1),
        )

        async with session_factory() as db:
            await _seed_project(
                db,
                draft_version=1,
                draft_payload=initial_payload,
                draft_saved_by_user_id=OWNER_USER_ID,
                version_rows=[
                    _make_version(
                        version=1,
                        created_by_user_id=OWNER_USER_ID,
                        checkpoint_reason="manual_save",
                        payload=initial_payload,
                        created_at=FIXED_UPDATED_AT,
                    )
                ],
            )

        reordered_payload = _project_payload_reordered(editor_zoom=1)
        async with session_factory() as db:
            response = await service.put_project_draft(
                db,
                WORKSPACE_A_ID,
                PROJECT_ID,
                ProjectDraftPutRequest(
                    version=1,
                    draft_schema_version="heygenx/v1",
                    base_project_updated_at=FIXED_UPDATED_AT,
                    draft_payload=reordered_payload,
                    checkpoint_reason="manual_save",
                ),
                OTHER_USER_ID,
            )
            await db.commit()

            assert response.version == 2
            assert response.last_saved_by_user_id == OTHER_USER_ID

            draft_row = (
                await db.execute(select(ProjectDraft).where(ProjectDraft.project_id == PROJECT_ID))
            ).scalar_one()
            version_rows = (
                await db.execute(select(ProjectVersion).where(ProjectVersion.project_id == PROJECT_ID))
            ).scalars().all()

            assert draft_row.version == 2
            assert draft_row.last_saved_by_user_id == OTHER_USER_ID
            assert draft_row.draft_payload == _merged_payload(
                project_name="Demo project",
                project_status="draft",
                source_language="en",
                target_language="es",
                payload=reordered_payload,
            )
            assert len(version_rows) == 1
            assert version_rows[0].version == 1
            assert version_rows[0].created_by_user_id == OWNER_USER_ID


@pytest.mark.asyncio
async def test_project_versions_are_workspace_scoped_and_missing_versions_error() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()

        version_one_payload = _merged_payload(
            project_name="Demo project",
            project_status="draft",
            source_language="en",
            target_language="es",
            payload=_project_payload(editor_zoom=1),
        )
        version_two_payload = _merged_payload(
            project_name="Demo project",
            project_status="draft",
            source_language="en",
            target_language="es",
            payload=_project_payload(editor_zoom=2),
        )

        async with session_factory() as db:
            await _seed_project(
                db,
                draft_version=2,
                draft_payload=version_two_payload,
                version_rows=[
                    _make_version(
                        version=1,
                        checkpoint_reason="manual_save",
                        payload=version_one_payload,
                        created_at=FIXED_CREATED_AT,
                    ),
                    _make_version(
                        version=2,
                        checkpoint_reason="manual_save",
                        payload=version_two_payload,
                        created_at=FIXED_SAVE_AT,
                    ),
                ],
            )
            await _seed_project(
                db,
                project_id=SECOND_PROJECT_ID,
                workspace_id=WORKSPACE_B_ID,
                name="Other workspace project",
                transcript_id=None,
                draft_version=1,
                draft_payload=version_one_payload,
                version_rows=[
                    _make_version(
                        version=1,
                        project_id=SECOND_PROJECT_ID,
                        workspace_id=WORKSPACE_B_ID,
                        payload=version_one_payload,
                        created_at=FIXED_CREATED_AT,
                    )
                ],
            )

        async with session_factory() as db:
            versions = await service.list_project_versions(
                db,
                WORKSPACE_A_ID,
                PROJECT_ID,
                OWNER_USER_ID,
            )
            assert [item.version for item in versions.items] == [2, 1]
            assert [item.created_by_user_id for item in versions.items] == [OWNER_USER_ID, OWNER_USER_ID]

            snapshot = await service.get_project_version(
                db,
                WORKSPACE_A_ID,
                PROJECT_ID,
                version_number=2,
                actor_user_id=OWNER_USER_ID,
            )
            assert snapshot.version == 2
            assert snapshot.draft_payload == version_two_payload

            with pytest.raises(ProjectNotFoundError):
                await service.get_project_version(
                    db,
                    WORKSPACE_A_ID,
                    PROJECT_ID,
                    version_number=99,
                    actor_user_id=OWNER_USER_ID,
                )

            with pytest.raises(ProjectNotFoundError):
                await service.list_project_versions(
                    db,
                    WORKSPACE_B_ID,
                    PROJECT_ID,
                    OWNER_USER_ID,
                )


@pytest.mark.asyncio
async def test_checkpoint_prunes_old_versions_but_keeps_latest_fifty_previous_snapshots() -> None:
    async with _project_db() as session_factory:
        service = ProjectService()
        service._utcnow = lambda: FIXED_SAVE_AT

        existing_versions = [
            _make_version(
                version=index,
                payload=_merged_payload(
                    project_name="Demo project",
                    project_status="draft",
                    source_language="en",
                    target_language="es",
                    payload=_project_payload(editor_zoom=index),
                ),
                created_at=datetime(2026, 9, 3, 8, 0, 0),
            )
            for index in range(1, 52)
        ]

        async with session_factory() as db:
            await _seed_project(
                db,
                draft_version=51,
                draft_payload=existing_versions[-1].draft_payload,
                draft_saved_by_user_id=OWNER_USER_ID,
                draft_updated_at=FIXED_SAVE_AT,
                version_rows=existing_versions,
            )

        async with session_factory() as db:
            response = await service.put_project_draft(
                db,
                WORKSPACE_A_ID,
                PROJECT_ID,
                ProjectDraftPutRequest(
                    version=51,
                    draft_schema_version="heygenx/v1",
                    base_project_updated_at=FIXED_SAVE_AT,
                    draft_payload=_project_payload(editor_zoom=999),
                    checkpoint_reason="manual_save",
                ),
                OTHER_USER_ID,
            )
            await db.commit()

            assert response.version == 52
            version_numbers = list(
                (await db.execute(
                    select(ProjectVersion.version)
                    .where(ProjectVersion.project_id == PROJECT_ID)
                    .order_by(ProjectVersion.version.desc())
                )).scalars().all()
            )
            assert version_numbers == list(range(52, 1, -1))

            oldest_version = await db.scalar(
                select(ProjectVersion).where(
                    ProjectVersion.project_id == PROJECT_ID,
                    ProjectVersion.version == 1,
                )
            )
            latest_version = await db.scalar(
                select(ProjectVersion).where(
                    ProjectVersion.project_id == PROJECT_ID,
                    ProjectVersion.version == 52,
                )
            )
            assert oldest_version is None
            assert latest_version is not None
            assert latest_version.created_by_user_id == OTHER_USER_ID
