"""Internal Cloud Tasks HTTP handlers (not for browser clients)."""

from __future__ import annotations

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
from app.services.translation_service import translation_service
from app.tasks.transcription_tasks import run_transcription_pipeline

logger = logging.getLogger("internal_tasks")
router = APIRouter(prefix="/internal/tasks", tags=["Internal Tasks"])


class TranscribeTaskPayload(BaseModel):
    media_id: uuid.UUID
    transcript_id: uuid.UUID
    language: Optional[str] = None
    max_speakers: Optional[int] = None
    enable_noise_reduction: bool = True
    enable_loudness_norm: bool = True
    job_id: str = Field(..., min_length=8)


class TranslateProjectTaskPayload(BaseModel):
    transcript_id: uuid.UUID
    source_language: str = "en"
    target_language: str
    project_id: Optional[uuid.UUID] = None
    job_id: str = Field(..., min_length=8)


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
    _: None = Depends(_verify_cloud_tasks_request),
):
    result = run_transcription_pipeline(
        media_id_str=str(payload.media_id),
        transcript_id_str=str(payload.transcript_id),
        language=payload.language,
        max_speakers=payload.max_speakers,
        enable_noise_reduction=payload.enable_noise_reduction,
        enable_loudness_norm=payload.enable_loudness_norm,
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

    translated = await translation_service.translate_segments_batch_async(
        segments=segments,
        source_language=payload.source_language,
        target_language=payload.target_language,
        project_id=payload.project_id,
        concurrency_limit=5,
    )

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
