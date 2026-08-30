import hashlib
import math
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import aiofiles
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.auth import (
    AuthenticatedRequestContext,
    ensure_workspace_resource_access,
    get_scoped_project,
    get_request_context,
    require_workspace_write_context,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.media import MediaFile, UploadChunk, UploadSession
from app.schemas.media_schema import (
    ChunkUploadResponse,
    CompleteUploadRequest,
    InitResumableUploadRequest,
    InitResumableUploadResponse,
    InitSignedUploadRequest,
    InitSignedUploadResponse,
    MediaFileResponse,
    UploadStatusResponse,
)
from app.services.media_service import media_service
from app.services.storage_service import storage_service
from app.utils.error_codes import (
    ChecksumMismatchException,
    ErrorCode,
    FileTooLargeException,
    MediaAppException,
    UploadSessionExpiredException,
)
from app.utils.file_validators import (
    calculate_sha256,
    detect_mime_type_from_header,
    validate_file_metadata,
)

router = APIRouter(prefix="/media", tags=["Media Upload & Ingestion"])


# =============================================================================
# 1. DIRECT MULTIPART UPLOAD (For files < 100MB)
# =============================================================================
@router.post(
    "/uploads/direct",
    response_model=MediaFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Direct Single-Part File Upload",
)
async def upload_direct_file(
    file: UploadFile = File(...),
    project_id: Optional[uuid.UUID] = Query(None),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Directly uploads media files (<100MB), validates codecs/format, and registers in database."""
    effective_project_id = None
    if project_id is not None:
        project = await get_scoped_project(
            project_id=project_id,
            db=db,
            context=context,
            require_write=True,
            not_found_detail="Project not found.",
        )
        effective_project_id = project.id

    temp_file_path = os.path.join(settings.TEMP_UPLOAD_DIR, f"{uuid.uuid4().hex}_{file.filename}")
    sha256_hasher = hashlib.sha256()
    total_bytes = 0

    try:
        # Stream file to disk while calculating hash and checking size limit
        async with aiofiles.open(temp_file_path, "wb") as out_file:
            # Read first chunk for magic bytes inspection
            first_chunk = await file.read(65536)
            if not first_chunk:
                raise MediaAppException(
                    status_code=400,
                    error_code=ErrorCode.INVALID_FORMAT,
                    message="Uploaded file is empty.",
                )
            
            detected_mime = detect_mime_type_from_header(first_chunk, file.filename or "media.mp4")
            validate_file_metadata(file.filename or "", 0, detected_mime, settings.MAX_FILE_SIZE_BYTES)
            
            await out_file.write(first_chunk)
            sha256_hasher.update(first_chunk)
            total_bytes += len(first_chunk)

            while chunk := await file.read(1024 * 1024):  # 1MB buffer
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_FILE_SIZE_BYTES:
                    raise FileTooLargeException(settings.MAX_FILE_SIZE_BYTES, total_bytes)
                await out_file.write(chunk)
                sha256_hasher.update(chunk)

        final_checksum = sha256_hasher.hexdigest()

        # Probe metadata with ffprobe
        metadata = await media_service.probe_media_file(temp_file_path)

        # Upload to permanent object store
        storage_key = media_service.generate_storage_key(file.filename or "media.mp4")
        await storage_service.upload_file(
            file_path=temp_file_path,
            key=storage_key,
            mime_type=metadata.mime_type,
        )

        # Generate thumbnail if video
        thumbnail_key = None
        if metadata.media_type == "video":
            thumbnail_key = await media_service.generate_thumbnail(temp_file_path, storage_key)

        # Persist MediaFile entity
        media_record = MediaFile(
            project_id=effective_project_id,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            storage_provider=settings.STORAGE_PROVIDER,
            storage_bucket=settings.GCS_BUCKET_NAME,
            storage_path=storage_key,
            thumbnail_path=thumbnail_key,
            original_filename=file.filename or "media.mp4",
            filesize_bytes=total_bytes,
            mime_type=metadata.mime_type,
            media_type=metadata.media_type,
            checksum_sha256=final_checksum,
            duration_seconds=metadata.duration_seconds,
            video_codec=metadata.video.codec if metadata.video else None,
            audio_codec=metadata.audio.codec if metadata.audio else None,
            frame_rate=metadata.video.frame_rate if metadata.video else None,
            resolution_width=metadata.video.resolution_width if metadata.video else None,
            resolution_height=metadata.video.resolution_height if metadata.video else None,
            audio_channels=metadata.audio.channels if metadata.audio else None,
            sample_rate=metadata.audio.sample_rate if metadata.audio else None,
            bitrate_kbps=metadata.video.bitrate_kbps if metadata.video else (metadata.audio.bitrate_kbps if metadata.audio else None),
            status="ready",
        )
        db.add(media_record)
        await db.commit()
        await db.refresh(media_record)

        thumbnail_url = storage_service.generate_presigned_download_url(thumbnail_key) if thumbnail_key else None

        resolution_str = f"{media_record.resolution_width}x{media_record.resolution_height}" if media_record.resolution_width else None

        return MediaFileResponse(
            media_id=media_record.id,
            filename=media_record.original_filename,
            media_type=media_record.media_type,
            mime_type=media_record.mime_type,
            filesize_bytes=media_record.filesize_bytes,
            duration_seconds=float(media_record.duration_seconds),
            resolution=resolution_str,
            video_codec=media_record.video_codec,
            audio_codec=media_record.audio_codec,
            frame_rate=float(media_record.frame_rate) if media_record.frame_rate else None,
            storage_path=media_record.storage_path,
            thumbnail_url=thumbnail_url,
            status=media_record.status,
            created_at=media_record.created_at,
        )

    finally:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass


# =============================================================================
# 2. RESUMABLE CHUNKED UPLOAD PIPELINE (For 4GB+ files)
# =============================================================================
@router.post(
    "/uploads/resumable",
    response_model=InitResumableUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Resumable Chunked Upload Session",
)
async def init_resumable_upload(
    req: InitResumableUploadRequest,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Initializes a resumable chunked upload session for massive video/audio files."""
    validate_file_metadata(req.filename, req.filesize_bytes, req.mime_type, settings.MAX_FILE_SIZE_BYTES)

    chunk_size = req.chunk_size_bytes or settings.MULTIPART_CHUNK_SIZE_BYTES
    total_chunks = math.ceil(req.filesize_bytes / chunk_size)
    storage_key = media_service.generate_storage_key(req.filename)

    # Initialize S3 Multipart Upload
    s3_upload_id = storage_service.initiate_multipart_upload(
        key=storage_key,
        mime_type=req.mime_type,
        metadata={"original_filename": req.filename, "filesize": str(req.filesize_bytes)},
    )

    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    session = UploadSession(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        filename=req.filename,
        filesize_bytes=req.filesize_bytes,
        mime_type=req.mime_type,
        total_chunks=total_chunks,
        chunk_size_bytes=chunk_size,
        bytes_received=0,
        storage_provider=settings.STORAGE_PROVIDER,
        storage_bucket=settings.GCS_BUCKET_NAME,
        storage_key=storage_key,
        s3_upload_id=s3_upload_id,
        status="in_progress",
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return InitResumableUploadResponse(
        upload_id=session.id,
        filename=session.filename,
        filesize_bytes=session.filesize_bytes,
        chunk_size_bytes=session.chunk_size_bytes,
        total_chunks=session.total_chunks,
        storage_path=session.storage_key,
        expires_at=session.expires_at,
        upload_mode="proxy_chunks",
    )


# =============================================================================
# 2b. DIRECT GCS RESUMABLE UPLOAD (browser → GCS, API stays out of the data path)
# =============================================================================
@router.post(
    "/uploads/signed-resumable",
    response_model=InitSignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Direct GCS Resumable Upload",
)
async def init_signed_resumable_upload(
    req: InitSignedUploadRequest,
    request: Request,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Issues a GCS resumable upload URL so multi-GB files never stream through Cloud Run."""
    validate_file_metadata(req.filename, req.filesize_bytes, req.mime_type, settings.MAX_FILE_SIZE_BYTES)

    storage_key = media_service.generate_storage_key(req.filename)
    origin = req.origin or request.headers.get("origin")
    gcs_url = storage_service.create_resumable_upload_url(
        key=storage_key,
        mime_type=req.mime_type,
        origin=origin,
        size_bytes=req.filesize_bytes,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    session = UploadSession(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        filename=req.filename,
        filesize_bytes=req.filesize_bytes,
        mime_type=req.mime_type,
        total_chunks=1,
        chunk_size_bytes=req.filesize_bytes,
        bytes_received=0,
        storage_provider=settings.STORAGE_PROVIDER,
        storage_bucket=settings.GCS_BUCKET_NAME,
        storage_key=storage_key,
        s3_upload_id="gcs-resumable",
        status="in_progress",
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return InitSignedUploadResponse(
        upload_id=session.id,
        filename=session.filename,
        filesize_bytes=session.filesize_bytes,
        storage_path=session.storage_key,
        gcs_resumable_url=gcs_url,
        expires_at=session.expires_at,
    )


@router.post(
    "/uploads/signed-resumable/{upload_id}/complete",
    response_model=MediaFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Finalize Direct GCS Resumable Upload",
)
async def complete_signed_resumable_upload(
    upload_id: uuid.UUID = Path(...),
    req: Optional[CompleteUploadRequest] = None,
    project_id: Optional[uuid.UUID] = Query(None),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Registers the MediaFile after the browser finished uploading directly to GCS."""
    stmt = select(UploadSession).where(UploadSession.id == upload_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise MediaAppException(
            status_code=404,
            error_code=ErrorCode.UPLOAD_SESSION_NOT_FOUND,
            message="Upload session not found.",
        )

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=session.workspace_id,
        require_write=True,
        not_found_detail="Upload session not found.",
    )

    effective_project_id = None
    if project_id is not None:
        project = await get_scoped_project(
            project_id=project_id,
            db=db,
            context=context,
            require_write=True,
            not_found_detail="Project not found.",
        )
        effective_project_id = project.id

    if session.status == "completed" and session.media_file_id:
        media_stmt = select(MediaFile).where(MediaFile.id == session.media_file_id)
        m_res = await db.execute(media_stmt)
        existing_media = m_res.scalar_one_or_none()
        if existing_media:
            return _format_media_response(existing_media)

    if not storage_service.object_exists(session.storage_key):
        raise MediaAppException(
            status_code=400,
            error_code=ErrorCode.STORAGE_UPLOAD_FAILED,
            message="GCS object not found. Finish the resumable upload before completing.",
            details={"storage_path": session.storage_key},
        )

    temp_probe_path = os.path.join(
        settings.TEMP_UPLOAD_DIR, f"probe_{session.id.hex}_{session.filename}"
    )
    thumbnail_key = None
    try:
        await storage_service.download_file(session.storage_key, temp_probe_path)
        if req and req.final_checksum_sha256:
            calculated_hash = calculate_sha256(temp_probe_path)
            if calculated_hash != req.final_checksum_sha256.lower():
                raise ChecksumMismatchException(req.final_checksum_sha256, calculated_hash)
            session.final_checksum_sha256 = calculated_hash
        else:
            session.final_checksum_sha256 = calculate_sha256(temp_probe_path)

        metadata = await media_service.probe_media_file(temp_probe_path)
        if metadata.media_type == "video":
            thumbnail_key = await media_service.generate_thumbnail(
                temp_probe_path, session.storage_key
            )
    finally:
        if os.path.exists(temp_probe_path):
            try:
                os.remove(temp_probe_path)
            except Exception:
                pass

    media_record = MediaFile(
        project_id=effective_project_id,
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        storage_provider=session.storage_provider,
        storage_bucket=session.storage_bucket,
        storage_path=session.storage_key,
        thumbnail_path=thumbnail_key,
        original_filename=session.filename,
        filesize_bytes=session.filesize_bytes,
        mime_type=session.mime_type,
        media_type=metadata.media_type,
        checksum_sha256=session.final_checksum_sha256,
        duration_seconds=metadata.duration_seconds,
        video_codec=metadata.video.codec if metadata.video else None,
        audio_codec=metadata.audio.codec if metadata.audio else None,
        frame_rate=metadata.video.frame_rate if metadata.video else None,
        resolution_width=metadata.video.resolution_width if metadata.video else None,
        resolution_height=metadata.video.resolution_height if metadata.video else None,
        audio_channels=metadata.audio.channels if metadata.audio else None,
        sample_rate=metadata.audio.sample_rate if metadata.audio else None,
        bitrate_kbps=(
            metadata.video.bitrate_kbps
            if metadata.video
            else (metadata.audio.bitrate_kbps if metadata.audio else None)
        ),
        status="ready",
    )
    db.add(media_record)
    await db.flush()
    session.status = "completed"
    session.bytes_received = session.filesize_bytes
    session.media_file_id = media_record.id
    await db.commit()
    await db.refresh(media_record)
    return _format_media_response(media_record)


@router.put(
    "/uploads/resumable/{upload_id}/chunk",
    response_model=ChunkUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Individual Binary Chunk",
)
async def upload_resumable_chunk(
    upload_id: uuid.UUID = Path(...),
    content_range: str = Header(..., alias="Content-Range"),
    x_chunk_index: int = Header(..., alias="X-Chunk-Index"),
    x_checksum_sha256: Optional[str] = Header(None, alias="X-Checksum-SHA256"),
    request: Request = None,
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Uploads a specific binary chunk part. Validates Content-Range and checksum."""
    # Find session
    stmt = select(UploadSession).where(UploadSession.id == upload_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise MediaAppException(
            status_code=404,
            error_code=ErrorCode.UPLOAD_SESSION_NOT_FOUND,
            message="Upload session not found.",
        )

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=session.workspace_id,
        require_write=True,
        not_found_detail="Upload session not found.",
    )

    if session.status != "in_progress" or session.expires_at < datetime.now(timezone.utc):
        raise UploadSessionExpiredException(str(upload_id))

    # Read chunk data
    chunk_data = await request.body()
    chunk_size = len(chunk_data)

    if chunk_size == 0:
        raise MediaAppException(
            status_code=400,
            error_code=ErrorCode.CHUNK_TOO_SMALL,
            message="Uploaded chunk payload is empty.",
        )

    # Verify Chunk SHA-256 Checksum if provided
    calculated_chunk_hash = hashlib.sha256(chunk_data).hexdigest()
    if x_checksum_sha256 and x_checksum_sha256.lower() != calculated_chunk_hash:
        raise ChecksumMismatchException(expected=x_checksum_sha256, calculated=calculated_chunk_hash)

    # S3 part numbers are 1-indexed (part 1 to 10000)
    part_number = x_chunk_index + 1

    # Upload part to storage provider
    etag = storage_service.upload_part(
        key=session.storage_key,
        upload_id=session.s3_upload_id,
        part_number=part_number,
        data=chunk_data,
    )

    # Parse byte range "bytes 0-8388607/4294967296"
    try:
        range_spec = content_range.replace("bytes ", "").split("/")[0]
        start_byte, end_byte = map(int, range_spec.split("-"))
    except Exception:
        start_byte = x_chunk_index * session.chunk_size_bytes
        end_byte = start_byte + chunk_size - 1

    # Upsert chunk record
    chunk_stmt = select(UploadChunk).where(
        UploadChunk.session_id == upload_id,
        UploadChunk.chunk_index == x_chunk_index,
    )
    chunk_res = await db.execute(chunk_stmt)
    existing_chunk = chunk_res.scalar_one_or_none()

    if existing_chunk:
        existing_chunk.etag = etag
        existing_chunk.checksum_sha256 = calculated_chunk_hash
        existing_chunk.size_bytes = chunk_size
    else:
        new_chunk = UploadChunk(
            session_id=upload_id,
            chunk_index=x_chunk_index,
            byte_start=start_byte,
            byte_end=end_byte,
            size_bytes=chunk_size,
            etag=etag,
            checksum_sha256=calculated_chunk_hash,
        )
        db.add(new_chunk)
        session.bytes_received += chunk_size

    await db.commit()

    progress = min(100.0, round((session.bytes_received / session.filesize_bytes) * 100, 2))
    is_completed = session.bytes_received >= session.filesize_bytes

    return ChunkUploadResponse(
        upload_id=session.id,
        chunk_index=x_chunk_index,
        bytes_received=session.bytes_received,
        total_bytes=session.filesize_bytes,
        progress_percent=progress,
        is_completed=is_completed,
    )


@router.get(
    "/uploads/resumable/{upload_id}/status",
    response_model=UploadStatusResponse,
    summary="Get Upload Progress & Missing Chunks",
)
async def get_resumable_upload_status(
    upload_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Returns detailed session status including which chunk indices are complete and which are missing."""
    stmt = (
        select(UploadSession)
        .options(selectinload(UploadSession.chunks))
        .where(UploadSession.id == upload_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise MediaAppException(
            status_code=404,
            error_code=ErrorCode.UPLOAD_SESSION_NOT_FOUND,
            message="Upload session not found.",
        )

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=session.workspace_id,
        not_found_detail="Upload session not found.",
    )

    completed_chunk_indices = set(c.chunk_index for c in session.chunks)
    all_indices = set(range(session.total_chunks))
    missing_indices = sorted(list(all_indices - completed_chunk_indices))

    progress = min(100.0, round((session.bytes_received / session.filesize_bytes) * 100, 2))

    return UploadStatusResponse(
        upload_id=session.id,
        status=session.status,
        filename=session.filename,
        bytes_received=session.bytes_received,
        total_bytes=session.filesize_bytes,
        total_chunks=session.total_chunks,
        completed_chunks=sorted(list(completed_chunk_indices)),
        missing_chunks=missing_indices,
        progress_percent=progress,
        expires_at=session.expires_at,
    )


@router.post(
    "/uploads/resumable/{upload_id}/complete",
    response_model=MediaFileResponse,
    summary="Finalize Resumable Upload & Probe Metadata",
)
async def complete_resumable_upload(
    upload_id: uuid.UUID = Path(...),
    req: Optional[CompleteUploadRequest] = None,
    project_id: Optional[uuid.UUID] = Query(None),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Finalizes S3/GCS multipart upload assembly, probes media with ffprobe, and registers the MediaFile."""
    stmt = (
        select(UploadSession)
        .options(selectinload(UploadSession.chunks))
        .where(UploadSession.id == upload_id)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise MediaAppException(
            status_code=404,
            error_code=ErrorCode.UPLOAD_SESSION_NOT_FOUND,
            message="Upload session not found.",
        )

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=session.workspace_id,
        require_write=True,
        not_found_detail="Upload session not found.",
    )

    effective_project_id = None
    if project_id is not None:
        project = await get_scoped_project(
            project_id=project_id,
            db=db,
            context=context,
            require_write=True,
            not_found_detail="Project not found.",
        )
        effective_project_id = project.id

    if session.status == "completed" and session.media_file_id:
        media_stmt = select(MediaFile).where(MediaFile.id == session.media_file_id)
        m_res = await db.execute(media_stmt)
        existing_media = m_res.scalar_one_or_none()
        if existing_media:
            return _format_media_response(existing_media)

    # Validate that all chunks are present
    uploaded_indices = set(c.chunk_index for c in session.chunks)
    expected_indices = set(range(session.total_chunks))
    if uploaded_indices != expected_indices:
        missing = sorted(list(expected_indices - uploaded_indices))
        raise MediaAppException(
            status_code=400,
            error_code=ErrorCode.CHUNK_OUT_OF_ORDER,
            message=f"Cannot complete upload. Missing {len(missing)} chunks.",
            details={"missing_chunks": missing[:20]},
        )

    # Assemble parts list for S3/MinIO
    parts = [
        {"PartNumber": chunk.chunk_index + 1, "ETag": chunk.etag}
        for chunk in session.chunks
    ]

    # Complete multipart upload in storage provider
    storage_service.complete_multipart_upload(
        key=session.storage_key,
        upload_id=session.s3_upload_id,
        parts=parts,
    )

    # Download small initial segment or inspect file to probe metadata
    temp_probe_path = os.path.join(settings.TEMP_UPLOAD_DIR, f"probe_{session.id.hex}_{session.filename}")
    thumbnail_key = None
    try:
        # Download file to verify streams & generate thumbnail
        await storage_service.download_file(session.storage_key, temp_probe_path)
        
        # Verify whole file SHA-256 if requested
        if req and req.final_checksum_sha256:
            calculated_hash = calculate_sha256(temp_probe_path)
            if calculated_hash != req.final_checksum_sha256.lower():
                raise ChecksumMismatchException(req.final_checksum_sha256, calculated_hash)
            session.final_checksum_sha256 = calculated_hash
        else:
            session.final_checksum_sha256 = calculate_sha256(temp_probe_path)

        # Probe metadata
        metadata = await media_service.probe_media_file(temp_probe_path)

        # Generate thumbnail
        if metadata.media_type == "video":
            thumbnail_key = await media_service.generate_thumbnail(temp_probe_path, session.storage_key)

    finally:
        if os.path.exists(temp_probe_path):
            try:
                os.remove(temp_probe_path)
            except Exception:
                pass

    # Create MediaFile database entry
    media_record = MediaFile(
        project_id=effective_project_id,
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        storage_provider=session.storage_provider,
        storage_bucket=session.storage_bucket,
        storage_path=session.storage_key,
        thumbnail_path=thumbnail_key,
        original_filename=session.filename,
        filesize_bytes=session.filesize_bytes,
        mime_type=session.mime_type,
        media_type=metadata.media_type,
        checksum_sha256=session.final_checksum_sha256,
        duration_seconds=metadata.duration_seconds,
        video_codec=metadata.video.codec if metadata.video else None,
        audio_codec=metadata.audio.codec if metadata.audio else None,
        frame_rate=metadata.video.frame_rate if metadata.video else None,
        resolution_width=metadata.video.resolution_width if metadata.video else None,
        resolution_height=metadata.video.resolution_height if metadata.video else None,
        audio_channels=metadata.audio.channels if metadata.audio else None,
        sample_rate=metadata.audio.sample_rate if metadata.audio else None,
        bitrate_kbps=metadata.video.bitrate_kbps if metadata.video else (metadata.audio.bitrate_kbps if metadata.audio else None),
        status="ready",
    )
    db.add(media_record)
    await db.flush()

    session.status = "completed"
    session.media_file_id = media_record.id
    await db.commit()
    await db.refresh(media_record)

    return _format_media_response(media_record)


@router.delete(
    "/uploads/resumable/{upload_id}/abort",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abort Resumable Upload Session",
)
async def abort_resumable_upload(
    upload_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(require_workspace_write_context),
    db: AsyncSession = Depends(get_db),
):
    """Cancels upload session, purges S3 multipart cache, and updates status to aborted."""
    stmt = select(UploadSession).where(UploadSession.id == upload_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session:
        await ensure_workspace_resource_access(
            db=db,
            context=context,
            workspace_id=session.workspace_id,
                require_write=True,
            not_found_detail="Upload session not found.",
        )
        storage_service.abort_multipart_upload(session.storage_key, session.s3_upload_id)
        session.status = "aborted"
        await db.commit()


@router.get(
    "/{media_id}",
    response_model=MediaFileResponse,
    summary="Get Media File Details & Playback URL",
)
async def get_media_file(
    media_id: uuid.UUID = Path(...),
    context: AuthenticatedRequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves metadata and presigned download URL for an ingested media file."""
    stmt = select(MediaFile).where(MediaFile.id == media_id)
    result = await db.execute(stmt)
    media = result.scalar_one_or_none()

    if not media:
        raise HTTPException(status_code=404, detail="Media file not found.")

    await ensure_workspace_resource_access(
        db=db,
        context=context,
        workspace_id=media.workspace_id,
        project_id=media.project_id,
        not_found_detail="Media file not found.",
    )

    return _format_media_response(media)


def _format_media_response(media: MediaFile) -> MediaFileResponse:
    thumbnail_url = storage_service.generate_presigned_download_url(media.thumbnail_path) if media.thumbnail_path else None
    resolution_str = f"{media.resolution_width}x{media.resolution_height}" if media.resolution_width else None
    return MediaFileResponse(
        media_id=media.id,
        filename=media.original_filename,
        media_type=media.media_type,
        mime_type=media.mime_type,
        filesize_bytes=media.filesize_bytes,
        duration_seconds=float(media.duration_seconds),
        resolution=resolution_str,
        video_codec=media.video_codec,
        audio_codec=media.audio_codec,
        frame_rate=float(media.frame_rate) if media.frame_rate else None,
        storage_path=media.storage_path,
        thumbnail_url=thumbnail_url,
        status=media.status,
        created_at=media.created_at,
    )
