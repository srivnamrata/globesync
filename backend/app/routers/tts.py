import asyncio
import json
import uuid
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.auth import (
    AuthenticatedRequestContext,
    ensure_workspace_resource_access,
    get_request_context,
    get_scoped_project,
    require_workspace_write_context,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.generated_audio import GeneratedAudio
from app.models.transcript import Transcript
from app.models.translation import Translation
from app.schemas.tts_schema import (
    GeneratedAudioResponse,
    MasterDubbedAudioResponse,
    SynthesizeProjectTTSRequest,
    SynthesizeSegmentTTSRequest,
    TTSJobResponse,
)
from app.services.storage_service import storage_service
from app.services.pipeline_availability import require_background_pipelines
from app.services.tts_orchestrator import tts_orchestrator
from app.tasks.tts_tasks import synthesize_project_tts_task

router = APIRouter(prefix="/tts", tags=["Text-to-Speech"])


@router.post(
    "/synthesize-project",
    response_model=TTSJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Synthesize Project Dubbing Audio (Batch Celery Task)",
)
async def synthesize_project(
    req: SynthesizeProjectTTSRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    require_background_pipelines()
    """Enqueues async Celery batch TTS generation, duration retiming, and master audio mixing."""
    stmt = select(Transcript).where(Transcript.id == req.transcript_id)
    res = await db.execute(stmt)
    transcript = res.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=transcript.workspace_id,
        project_id=transcript.project_id,
        require_write=True,
        not_found_detail="Transcript not found.",
    )

    effective_project_id = transcript.project_id
    if req.project_id is not None:
        project = await get_scoped_project(
            project_id=req.project_id,
            db=db,
            context=context,
            require_write=True,
            not_found_detail="Project not found.",
        )
        effective_project_id = project.id

    proj_id_str = str(effective_project_id or "")
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    idempotency_key = f"tts-project:{req.transcript_id}:{req.target_language}"

    task = synthesize_project_tts_task.apply_async(
        kwargs={
            "transcript_id_str": str(req.transcript_id),
            "target_language": req.target_language,
            "project_id_str": proj_id_str,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        },
        queue="tts_clone",
    )

    return TTSJobResponse(
        job_id=task.id,
        transcript_id=req.transcript_id,
        target_language=req.target_language,
        status="queued",
        message="Parallel TTS speech generation and retiming task enqueued.",
    )


@router.post(
    "/synthesize-segment",
    response_model=GeneratedAudioResponse,
    summary="Synthesize & Retime Single Translation Segment",
)
async def synthesize_single_segment(
    req: SynthesizeSegmentTTSRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Synthesizes a single segment on-demand and applies pitch-preserving time-stretching."""
    stmt = select(Translation).where(Translation.id == req.translation_id)
    res = await db.execute(stmt)
    translation = res.scalar_one_or_none()

    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=translation.workspace_id,
        project_id=translation.project_id,
        require_write=True,
        not_found_detail="Translation not found.",
    )

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    gen_audio = await tts_orchestrator.synthesize_single_translation(
        translation,
        request_id=request_id,
        idempotency_key=f"tts-segment:{translation.id}",
    )
    gen_audio.project_id = translation.project_id
    gen_audio.workspace_id = context.workspace_id
    db.add(gen_audio)
    await db.commit()
    await db.refresh(gen_audio)

    audio_url = storage_service.generate_presigned_download_url(gen_audio.storage_path)

    return GeneratedAudioResponse(
        id=gen_audio.id,
        translation_id=gen_audio.translation_id,
        audio_url=audio_url,
        storage_path=gen_audio.storage_path,
        raw_tts_duration_ms=gen_audio.raw_tts_duration_ms,
        target_duration_ms=gen_audio.target_duration_ms,
        retimed_duration_ms=gen_audio.retimed_duration_ms,
        speed_adjustment_factor=float(gen_audio.speed_adjustment_factor),
        is_retimed=gen_audio.is_retimed,
        status=gen_audio.status,
        quality_score=float(gen_audio.quality_score),
        created_at=gen_audio.created_at,
    )


@router.get(
    "/project/{project_id}/master-audio",
    response_model=MasterDubbedAudioResponse,
    summary="Get Master Dubbed Audio Streaming URL",
)
async def get_master_audio(
    project_id: uuid.UUID = Path(...),
    target_language: str = Query("es"),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves presigned playback URL for the final master dubbed audio track."""
    await get_scoped_project(
        project_id=project_id,
        db=db,
        context=context,
        not_found_detail="Project not found.",
    )

    master_key = f"master_dubbed/{str(project_id)}/{target_language}_dubbed.wav"
    download_url = storage_service.generate_presigned_download_url(master_key, expires_in_seconds=7200)

    return MasterDubbedAudioResponse(
        project_id=project_id,
        transcript_id=project_id,
        target_language=target_language,
        master_audio_url=download_url,
        storage_path=master_key,
        status="ready",
    )


@router.get(
    "/{project_id}/stream",
    summary="Server-Sent Events (SSE) Live TTS Progress Feed",
)
async def stream_tts_progress(
    project_id: uuid.UUID = Path(...),
    request: Request = None,
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Streams live Redis Pub/Sub TTS synthesis progress events to the frontend."""
    await get_scoped_project(
        project_id=project_id,
        db=db,
        context=context,
        not_found_detail="Project not found.",
    )

    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:tts:{project_id}")

        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    data = message["data"].decode("utf-8")
                    yield f"event: progress\ndata: {data}\n\n"
                await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(f"events:tts:{project_id}")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
