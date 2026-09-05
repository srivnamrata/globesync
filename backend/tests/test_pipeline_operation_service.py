from __future__ import annotations

import uuid
from contextlib import contextmanager

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.types import TypeDecorator

from app.models.pipeline_operation import PipelineOperation
from app.services.pipeline_operation_service import checkpoint_operation


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


OPERATION_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
MISSING_OPERATION_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PROJECT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
WORKSPACE_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TRANSCRIPT_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _patch_sqlite_types():
    saved_types = []
    for column in PipelineOperation.__table__.columns:
        if isinstance(column.type, PGUUID):
            saved_types.append((column, column.type))
            column.type = SQLiteUUID()
    return saved_types


def _restore_sqlite_types(saved_types):
    for column, original_type in saved_types:
        column.type = original_type


@contextmanager
def _pipeline_db():
    saved_types = _patch_sqlite_types()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        PipelineOperation.__table__.create(engine, checkfirst=True)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        yield session_factory
    finally:
        engine.dispose()
        _restore_sqlite_types(saved_types)


def _seed_operation(
    session,
    *,
    operation_id: uuid.UUID = OPERATION_ID,
    status: str = "queued",
    current_stage: str = "queued",
    progress_percent: int = 0,
    last_successful_stage: str | None = None,
    message: str | None = None,
    error_message: str | None = None,
) -> PipelineOperation:
    operation = PipelineOperation(
        id=operation_id,
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        transcript_id=TRANSCRIPT_ID,
        operation_type="translation",
        target_language="es",
        status=status,
        progress_percent=progress_percent,
        current_stage=current_stage,
        last_successful_stage=last_successful_stage,
        message=message,
        error_message=error_message,
    )
    session.add(operation)
    session.commit()
    return operation


def test_checkpoint_operation_updates_status_progress_and_commits() -> None:
    with _pipeline_db() as session_factory:
        with session_factory() as session:
            _seed_operation(session)

        with session_factory() as session:
            commit_count = 0
            original_commit = session.commit

            def counting_commit():
                nonlocal commit_count
                commit_count += 1
                return original_commit()

            session.commit = counting_commit

            checkpoint_operation(
                session,
                OPERATION_ID,
                status="in_progress",
                stage="extract_audio",
                progress_percent=135,
                message="Extracting audio",
                successful_stage="extract_audio",
            )
            checkpoint_operation(
                session,
                OPERATION_ID,
                status="failed",
                stage="transcribe",
                progress_percent=-12,
                message="Transcription failed",
                successful_stage="extract_audio",
                error_message="boom",
            )

            refreshed = session.get(PipelineOperation, OPERATION_ID)
            assert commit_count == 2
            assert refreshed.status == "failed"
            assert refreshed.current_stage == "transcribe"
            assert refreshed.progress_percent == 0
            assert refreshed.message == "Transcription failed"
            assert refreshed.error_message == "boom"
            assert refreshed.last_successful_stage == "extract_audio"


def test_checkpoint_operation_noops_for_missing_ids_and_records() -> None:
    with _pipeline_db() as session_factory:
        with session_factory() as session:
            commit_count = 0
            original_commit = session.commit

            def counting_commit():
                nonlocal commit_count
                commit_count += 1
                return original_commit()

            session.commit = counting_commit

            checkpoint_operation(
                session,
                None,
                status="in_progress",
                stage="queued",
                progress_percent=50,
                message="ignored",
            )
            checkpoint_operation(
                session,
                MISSING_OPERATION_ID,
                status="in_progress",
                stage="queued",
                progress_percent=50,
                message="ignored",
                error_message="ignored",
            )

            assert commit_count == 0
            assert session.get(PipelineOperation, MISSING_OPERATION_ID) is None
