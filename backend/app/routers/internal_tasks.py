"""Internal Cloud Tasks HTTP handlers (not for browser clients)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.models.pipeline_operation import PipelineOperation
from app.services.translation_service import translation_service
from app.tasks.lipsync_tasks import run_lipsync_project_pipeline
from app.tasks.transcription_tasks import run_transcription_pipeline

logger = logging.getLogger("internal_tasks")
router = APIRouter(prefix="/internal/tasks", tags=["Internal Tasks"])


async def _checkpoint_translation_operation(
    db: AsyncSession,
    operation_id: str,
    *,
    status_value: str,
    progress_percent: int,
    message: str,
    error_message: Optional[str] = None,
) -> None:
    operation = await db.get(PipelineOperation, operation_id)
    if operation is None:
        return
    operation.status = status_value
    operation.current_stage = "translate"
    operation.progress_percent = progress_percent
    operation.message = message
    operation.error_message = error_message
    if status_value == "completed":
        operation.last_successful_stage = "translate"
    await db.commit()


class TranscribeTaskPayload(BaseModel):
    media_id: uuid.UUID
    transcript_id: uuid.UUID
    language: Optional[str] = None
    max_speakers: Optional[int] = None
    enable_noise_reduction: bool = True
    enable_loudness_norm: bool = True
    enable_vad: bool = True
    job_id: str = Field(..., min_length=8)
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    source_action: Optional[str] = None


class TranslateProjectTaskPayload(BaseModel):
    transcript_id: uuid.UUID
    source_language: str = "en"
    target_language: str
    project_id: Optional[uuid.UUID] = None
    job_id: str = Field(..., min_length=8)
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    operation_id: Optional[str] = None


class RenderLipSyncProjectTaskPayload(BaseModel):
    job_id: uuid.UUID
    media_file_id: uuid.UUID
    transcript_id: uuid.UUID
    target_language: str
    project_id: Optional[uuid.UUID] = None
    model_preference: str = "liveportrait"
    burn_in_subtitles: bool = False
    request_id: Optional[str] = None
    idempotency_key: Optional[str] = None


async def _verify_cloud_tasks_request(
    x_cloudtasks_taskname: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    authorization: Optional[str] = Header(None),
) -> None:
    """Accept Cloud Tasks deliveries; reject anonymous browser traffic."""
    if settings.DEPLOYMENT_ENV == "development" and not settings.CLOUD_TASKS_ENABLED:
        return
    if not x_cloudtasks_taskname:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal task endpoints accept Cloud Tasks deliveries only.",
        )
    # OIDC is enforced by Cloud Run IAM when --no-allow-unauthenticated / invoker
    # bindings are configured. Presence of the Cloud Tasks header is the app-level gate.
    _ = authorization


@router.post(
    "/transcribe",
    status_code=status.HTTP_200_OK,
    summary="Execute transcription pipeline (Cloud Tasks target)",
)
async def run_transcribe_task(
    payload: TranscribeTaskPayload,
    x_cloudtasks_taskname: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    _: None = Depends(_verify_cloud_tasks_request),
):
    result = await asyncio.to_thread(
        run_transcription_pipeline,
        media_id_str=str(payload.media_id),
        transcript_id_str=str(payload.transcript_id),
        language=payload.language,
        max_speakers=payload.max_speakers,
        enable_noise_reduction=payload.enable_noise_reduction,
        enable_loudness_norm=payload.enable_loudness_norm,
        request_id=payload.request_id or payload.job_id,
        task_id=x_cloudtasks_taskname or payload.job_id,
        idempotency_key=payload.idempotency_key,
        source_action=payload.source_action or "transcription_pipeline_cloud_task",
        operation_id=payload.job_id,
    )
    logger.info(
        "Cloud Tasks transcription job %s completed (%s)",
        payload.job_id,
        payload.transcript_id,
    )
    return {
        "status": result["status"],
        "job_id": payload.job_id,
        "transcript_id": str(payload.transcript_id),
        "segments": result["segments"],
    }


@router.post(
    "/translate-project",
    status_code=status.HTTP_200_OK,
    summary="Execute project translation (Cloud Tasks target)",
)
async def run_translate_project_task(
    payload: TranslateProjectTaskPayload,
    db: AsyncSession = Depends(get_db),
    x_cloudtasks_taskname: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    _: None = Depends(_verify_cloud_tasks_request),
):
    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == payload.transcript_id)
        .order_by(TranscriptSegment.sequence_order)
    )
    result = await db.execute(stmt)
    segments = list(result.scalars().all())
    if not segments:
        raise HTTPException(status_code=404, detail="No transcript segments found.")

    transcript_stmt = select(Transcript).where(Transcript.id == payload.transcript_id)
    transcript_result = await db.execute(transcript_stmt)
    transcript = transcript_result.scalar_one_or_none()
    workspace_id = transcript.workspace_id if transcript else None

    operation_id = payload.operation_id or str(payload.job_id)
    await _checkpoint_translation_operation(
        db,
        operation_id,
        status_value="in_progress",
        progress_percent=10,
        message="Loading transcript segments",
    )

    await _checkpoint_translation_operation(
        db,
        operation_id,
        status_value="in_progress",
        progress_percent=30,
        message=f"Translating {len(segments)} segments",
    )
    try:
        translated = await translation_service.translate_segments_batch_async(
            segments=segments,
            source_language=payload.source_language,
            target_language=payload.target_language,
            project_id=payload.project_id,
            workspace_id=workspace_id,
            request_id=payload.request_id or payload.job_id,
            task_id=x_cloudtasks_taskname or payload.job_id,
            source_action="translate_project_cloud_task",
            idempotency_key_prefix=payload.idempotency_key,
            concurrency_limit=5,
        )
    except Exception as exc:
        await _checkpoint_translation_operation(
            db,
            operation_id,
            status_value="failed",
            progress_percent=0,
            message="Translation failed",
            error_message=str(exc),
        )
        raise

    segment_ids = [s.id for s in segments]
    existing = await db.execute(
        select(Translation).where(
            Translation.transcript_segment_id.in_(segment_ids),
            Translation.target_language == payload.target_language,
        )
    )
    for row in existing.scalars().all():
        await db.delete(row)

    for entity in translated:
        db.add(entity)
    await db.commit()
    await _checkpoint_translation_operation(
        db,
        operation_id,
        status_value="completed",
        progress_percent=100,
        message=f"Translated {len(translated)} segments.",
    )

    logger.info(
        "Cloud Tasks translation job %s completed (%s segments → %s)",
        payload.job_id,
        len(translated),
        payload.target_language,
    )
    return {
        "status": "completed",
        "job_id": payload.job_id,
        "transcript_id": str(payload.transcript_id),
        "segments_translated": len(translated),
    }


@router.post(
    "/render-lipsync-project",
    status_code=status.HTTP_200_OK,
    summary="Execute dub and lip-sync pipeline (Cloud Tasks target)",
)
async def run_render_lipsync_project_task(
    payload: RenderLipSyncProjectTaskPayload,
    x_cloudtasks_taskname: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    _: None = Depends(_verify_cloud_tasks_request),
):
    result = await asyncio.to_thread(
        run_lipsync_project_pipeline,
        job_id_str=str(payload.job_id),
        media_file_id_str=str(payload.media_file_id),
        transcript_id_str=str(payload.transcript_id),
        target_language=payload.target_language,
        model_preference=payload.model_preference,
        burn_in_subtitles=payload.burn_in_subtitles,
        request_id=payload.request_id,
        task_id=x_cloudtasks_taskname or str(payload.job_id),
        idempotency_key=payload.idempotency_key,
    )
    logger.info(
        "Cloud Tasks dub/lip-sync job %s completed (%s)",
        payload.job_id,
        payload.transcript_id,
    )
    return result
