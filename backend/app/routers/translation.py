import asyncio
import json
import uuid
from typing import Optional
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
from fastapi.responses import PlainTextResponse, StreamingResponse
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.auth import (
    AuthenticatedRequestContext,
    ensure_workspace_resource_access,
    get_request_context,
    require_workspace_write_context,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.transcript import Transcript, TranscriptSegment
from app.models.translation import Translation
from app.schemas.translation_schema import (
    ProjectTranslationResponse,
    SupportedLanguagesResponse,
    SupportedLanguageResponse,
    TranslateProjectRequest,
    TranslateSegmentRequest,
    TranslationItemResponse,
    TranslationJobResponse,
    UpdateTranslationRequest,
)
from app.services.cloud_tasks_service import cloud_tasks_service
from app.services.duration_matcher import duration_matcher
from app.services.pipeline_availability import require_background_pipelines
from app.services.translation_service import translation_service
from app.utils.language_configs import get_supported_languages
from app.utils.speech_rate import speech_rate_estimator

router = APIRouter(prefix="/translation", tags=["Translation & Duration Matching"])


@router.get(
    "/languages",
    response_model=SupportedLanguagesResponse,
    summary="List Supported Translation Languages",
)
async def list_supported_translation_languages():
    return SupportedLanguagesResponse(
        languages=[
            SupportedLanguageResponse(
                code=language.code,
                name=language.name,
                native_name=language.native_name,
            )
            for language in get_supported_languages()
        ]
    )


@router.post(
    "/translate-project",
    response_model=TranslationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispatch Batch Project Translation",
)
async def translate_project(
    req: TranslateProjectRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Queue via Cloud Tasks, run inline (Google text), or Celery when a worker exists."""
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

    source_language = req.source_language or transcript.detected_language or "en"
    project_id = transcript.project_id
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    idempotency_key = f"translate-project:{req.transcript_id}:{req.target_language}"
    job_id = uuid.uuid4().hex

    # Preferred production path: Cloud Tasks → private internal API handler.
    if cloud_tasks_service.enabled:
        cloud_tasks_service.enqueue_http_task(
            relative_handler_path="/v1/internal/tasks/translate-project",
            payload={
                "transcript_id": str(req.transcript_id),
                "source_language": source_language,
                "target_language": req.target_language,
                "project_id": str(project_id) if project_id else None,
                "job_id": job_id,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            },
            task_name_suffix=f"translate-{req.transcript_id.hex}-{req.target_language}-{job_id[:12]}",
        )
        return TranslationJobResponse(
            job_id=job_id,
            transcript_id=req.transcript_id,
            target_language=req.target_language,
            status="queued",
            message="Batch translation queued on Cloud Tasks.",
        )

    # Two-service launch without Celery: run Google text translation in-request.
    if settings.TRANSLATION_SYNC_FALLBACK and not settings.ENABLE_BACKGROUND_PIPELINES:
        seg_stmt = (
            select(TranscriptSegment)
            .where(TranscriptSegment.transcript_id == req.transcript_id)
            .order_by(TranscriptSegment.sequence_order)
        )
        seg_res = await db.execute(seg_stmt)
        segments = list(seg_res.scalars().all())
        if not segments:
            raise HTTPException(status_code=404, detail="No transcript segments found.")

        translated = await translation_service.translate_segments_batch_async(
            segments=segments,
            source_language=source_language,
            target_language=req.target_language,
            project_id=project_id,
            workspace_id=context.workspace_id,
            request_id=request_id,
            task_id=job_id,
            source_action="translate_project_sync_fallback",
            idempotency_key_prefix=idempotency_key,
            concurrency_limit=5,
        )
        segment_ids = [s.id for s in segments]
        existing = await db.execute(
            select(Translation).where(
                Translation.transcript_segment_id.in_(segment_ids),
                Translation.target_language == req.target_language,
            )
        )
        for row in existing.scalars().all():
            await db.delete(row)
        for entity in translated:
            db.add(entity)
        await db.commit()

        return TranslationJobResponse(
            job_id=job_id,
            transcript_id=req.transcript_id,
            target_language=req.target_language,
            status="completed",
            message=f"Synchronously translated {len(translated)} segments.",
        )

    require_background_pipelines()
    from app.tasks.translation_tasks import translate_project_batch_task

    task = translate_project_batch_task.apply_async(
        kwargs={
            "transcript_id_str": str(req.transcript_id),
            "source_language": source_language,
            "target_language": req.target_language,
            "project_id_str": str(project_id) if project_id else None,
            "workspace_id_str": str(context.workspace_id),
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        },
        queue="translation",
    )

    return TranslationJobResponse(
        job_id=task.id,
        transcript_id=req.transcript_id,
        target_language=req.target_language,
        status="queued",
        message="Batch translation and duration matching pipeline queued.",
    )


@router.post(
    "/translate-segment",
    response_model=TranslationItemResponse,
    summary="Translate Single Segment with Iterative Duration Matching",
)
async def translate_single_segment(
    req: TranslateSegmentRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Translates a single segment and actively adjusts length to match target duration within ±10%."""
    stmt = (
        select(TranscriptSegment)
        .options(selectinload(TranscriptSegment.transcript))
        .where(TranscriptSegment.id == req.segment_id)
    )
    res = await db.execute(stmt)
    segment = res.scalar_one_or_none()

    if not segment:
        raise HTTPException(status_code=404, detail="Transcript segment not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=segment.transcript.workspace_id if segment.transcript else None,
        project_id=segment.transcript.project_id if segment.transcript else None,
        require_write=True,
        not_found_detail="Transcript segment not found.",
    )

    result = await duration_matcher.translate_with_duration_matching(
        source_text=req.source_text,
        original_duration_ms=req.original_duration_ms,
        source_language=req.source_language,
        target_language=req.target_language,
        speaker_tag=req.speaker_tag,
        previous_context=req.previous_context,
        next_context=req.next_context,
    )

    # Upsert Translation in DB
    trans_stmt = select(Translation).where(
        Translation.transcript_segment_id == req.segment_id,
        Translation.target_language == req.target_language,
    ).options(selectinload(Translation.generated_audio))
    t_res = await db.execute(trans_stmt)
    trans = t_res.scalar_one_or_none()

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    idempotency_key = f"translate-segment:{segment.id}:{req.target_language}"

    if not trans:
        trans = Translation(
            transcript_segment_id=segment.id,
            project_id=segment.transcript.project_id if segment.transcript else None,
            workspace_id=context.workspace_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            source_language=req.source_language,
            target_language=req.target_language,
            source_text=req.source_text,
            translated_text=result.translated_text,
            original_duration_ms=result.original_duration_ms,
            estimated_duration_ms=result.estimated_duration_ms,
            duration_ratio=result.duration_ratio,
            iterations_count=result.iterations_count,
            confidence_score=result.confidence_score,
            is_cached=result.is_cached,
            iteration_history=result.iteration_history,
            source_action="translate_single_segment",
        )
        db.add(trans)
    else:
        # A new translation invalidates every audio rendition derived from the
        # previous text. The next segment synthesis replaces the same storage
        # object, so removing these rows does not orphan additional objects.
        for generated_audio in trans.generated_audio:
            await db.delete(generated_audio)
        trans.request_id = request_id
        trans.idempotency_key = idempotency_key
        trans.source_action = "translate_single_segment"
        trans.translated_text = result.translated_text
        trans.estimated_duration_ms = result.estimated_duration_ms
        trans.duration_ratio = result.duration_ratio
        trans.iterations_count = result.iterations_count
        trans.confidence_score = result.confidence_score
        trans.is_cached = result.is_cached
        trans.iteration_history = result.iteration_history
        trans.source_text = req.source_text

    await db.commit()
    await db.refresh(trans)

    return _format_translation_item(trans, segment)


@router.get(
    "/{transcript_id}",
    response_model=ProjectTranslationResponse,
    summary="Get All Translations for Transcript & Target Language",
)
async def get_project_translations(
    transcript_id: uuid.UUID = Path(...),
    target_language: str = Query(..., examples=["es"]),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves all translated segments along with duration ratios and quality scores."""
    transcript_stmt = select(Transcript).where(Transcript.id == transcript_id)
    transcript_res = await db.execute(transcript_stmt)
    transcript = transcript_res.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=transcript.workspace_id,
        project_id=transcript.project_id,
        not_found_detail="Transcript not found.",
    )

    # Get all segments for transcript
    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.transcript_id == transcript_id)
        .order_by(TranscriptSegment.sequence_order)
    )
    res = await db.execute(stmt)
    segments = res.scalars().all()

    if not segments:
        raise HTTPException(status_code=404, detail="No transcript segments found.")

    segment_ids = [s.id for s in segments]
    seg_map = {s.id: s for s in segments}

    # Fetch translations
    t_stmt = select(Translation).where(
        Translation.transcript_segment_id.in_(segment_ids),
        Translation.target_language == target_language,
    ).options(selectinload(Translation.generated_audio))
    t_res = await db.execute(t_stmt)
    translations = t_res.scalars().all()

    trans_items = []
    ratio_sum = 0.0
    conf_sum = 0.0

    for t in translations:
        seg = seg_map.get(t.transcript_segment_id)
        if seg:
            item = _format_translation_item(t, seg)
            trans_items.append(item)
            ratio_sum += float(t.duration_ratio)
            conf_sum += float(t.confidence_score or 0.95)

    trans_items.sort(key=lambda x: x.sequence_order)
    total_count = len(trans_items)
    avg_ratio = round(ratio_sum / total_count, 3) if total_count > 0 else 1.0
    overall_conf = round(conf_sum / total_count, 4) if total_count > 0 else 0.95

    return ProjectTranslationResponse(
        transcript_id=transcript_id,
        target_language=target_language,
        total_segments=total_count,
        average_duration_ratio=avg_ratio,
        overall_confidence=overall_conf,
        translations=trans_items,
    )


@router.put(
    "/segment/{translation_id}",
    response_model=TranslationItemResponse,
    summary="Update Translated Text Manually with Duration Re-estimation",
)
async def update_translation(
    translation_id: uuid.UUID = Path(...),
    req: UpdateTranslationRequest = None,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Allows user to edit translated text. Re-calculates estimated speech duration in real-time."""
    stmt = (
        select(Translation)
        # The response includes generated-audio readiness. Load it before the
        # commit so response formatting never triggers a lazy database query
        # from the async request path.
        .options(
            selectinload(Translation.segment),
            selectinload(Translation.generated_audio),
        )
        .where(Translation.id == translation_id)
    )
    res = await db.execute(stmt)
    trans = res.scalar_one_or_none()

    if not trans:
        raise HTTPException(status_code=404, detail="Translation not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=trans.workspace_id,
        project_id=trans.project_id,
        require_write=True,
        not_found_detail="Translation not found.",
    )

    new_text = req.translated_text.strip()
    est_duration_ms = speech_rate_estimator.estimate_speech_duration_ms(new_text, trans.target_language)
    ratio, status_str = speech_rate_estimator.calculate_duration_delta(trans.original_duration_ms, est_duration_ms)

    trans.translated_text = new_text
    trans.estimated_duration_ms = est_duration_ms
    trans.duration_ratio = ratio
    trans.is_user_edited = True
    trans.speed_adjustment_factor = max(0.80, min(1.25, ratio))

    await db.commit()
    await db.refresh(trans)

    return _format_translation_item(trans, trans.segment)


@router.get(
    "/{transcript_id}/export/{export_format}",
    summary="Export Translated Subtitles (SRT, VTT, TXT)",
)
async def export_translated_subtitles(
    transcript_id: uuid.UUID = Path(...),
    export_format: str = Path(..., pattern="^(srt|vtt|txt)$"),
    target_language: str = Query("es"),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Exports translated subtitles in standard SRT or WebVTT format."""
    project_trans = await get_project_translations(transcript_id, target_language, context, db)
    items = project_trans.translations

    if export_format == "srt":
        srt_lines = []
        for i, item in enumerate(items, start=1):
            s_start = _sec_to_srt_time(item.start_time_seconds)
            s_end = _sec_to_srt_time(item.end_time_seconds)
            srt_lines.append(f"{i}\n{s_start} --> {s_end}\n[{item.speaker_tag}] {item.translated_text}\n")
        return Response(
            content="\n".join(srt_lines),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=subtitles_{target_language}.srt"},
        )
    elif export_format == "vtt":
        vtt_lines = ["WEBVTT\n"]
        for i, item in enumerate(items, start=1):
            s_start = _sec_to_vtt_time(item.start_time_seconds)
            s_end = _sec_to_vtt_time(item.end_time_seconds)
            vtt_lines.append(f"{i}\n{s_start} --> {s_end}\n<v {item.speaker_tag}>{item.translated_text}\n")
        return Response(
            content="\n".join(vtt_lines),
            media_type="text/vtt",
            headers={"Content-Disposition": f"attachment; filename=subtitles_{target_language}.vtt"},
        )
    else:  # txt
        txt_lines = [
            f"[{_sec_to_txt_time(item.start_time_seconds)}] {item.speaker_tag}: \"{item.translated_text}\""
            for item in items
        ]
        return PlainTextResponse(content="\n".join(txt_lines))


@router.get(
    "/{transcript_id}/stream",
    summary="Server-Sent Events (SSE) Translation Progress",
)
async def stream_translation_progress(
    transcript_id: uuid.UUID = Path(...),
    request: Request = None,
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Streams live Redis Pub/Sub translation progress events to frontend via SSE."""
    transcript_stmt = select(Transcript).where(Transcript.id == transcript_id)
    transcript_res = await db.execute(transcript_stmt)
    transcript = transcript_res.scalar_one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=transcript.workspace_id,
        project_id=transcript.project_id,
        not_found_detail="Transcript not found.",
    )

    async def event_generator():
        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"events:translation:{transcript_id}")

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
            await pubsub.unsubscribe(f"events:translation:{transcript_id}")
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


def _format_translation_item(trans: Translation, seg: TranscriptSegment) -> TranslationItemResponse:
    _, status_str = speech_rate_estimator.calculate_duration_delta(
        trans.original_duration_ms, trans.estimated_duration_ms
    )
    return TranslationItemResponse(
        translation_id=trans.id,
        segment_id=seg.id,
        sequence_order=seg.sequence_order,
        speaker_tag=seg.speaker_tag,
        start_time_seconds=float(seg.start_time_seconds),
        end_time_seconds=float(seg.end_time_seconds),
        source_text=trans.source_text,
        translated_text=trans.translated_text,
        original_duration_ms=trans.original_duration_ms,
        estimated_duration_ms=trans.estimated_duration_ms,
        duration_ratio=float(trans.duration_ratio),
        duration_status=status_str,
        iterations_count=trans.iterations_count,
        confidence_score=float(trans.confidence_score or 0.95),
        is_cached=trans.is_cached,
        is_user_edited=trans.is_user_edited,
        generated_audio_status=(trans.generated_audio[0].status if trans.generated_audio else None),
        created_at=trans.created_at,
    )


def _sec_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sec_to_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _sec_to_txt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
