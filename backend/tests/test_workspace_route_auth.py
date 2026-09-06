import asyncio
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from app.routers import export, lipsync, transcription, translation, tts, upload


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    def __init__(self, result):
        self._result = result
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _ScalarResult(self._result)


def _build_context(role: str = "editor"):
    return SimpleNamespace(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        membership_role=role,
    )


def _request():
    return SimpleNamespace(headers={})


def test_upload_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    upload_id = uuid.uuid4()
    session = SimpleNamespace(
        id=upload_id,
        workspace_id=uuid.uuid4(),
        chunks=[],
        total_chunks=1,
        bytes_received=0,
        filesize_bytes=1,
        filename="demo.mp4",
        status="in_progress",
        expires_at=None,
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == session.workspace_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(upload, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            upload.get_resumable_upload_status(
                upload_id=upload_id,
                context=context,
                db=FakeAsyncSession(session),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Upload session not found."


def test_transcription_get_transcript_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    transcript_id = uuid.uuid4()
    transcript_row = SimpleNamespace(
        id=transcript_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        segments=[],
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == transcript_row.workspace_id
        assert kwargs["project_id"] == transcript_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            transcription.get_transcript(
                transcript_id=transcript_id,
                context=context,
                db=FakeAsyncSession(transcript_row),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transcript not found."


def test_translation_translate_project_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    transcript_id = uuid.uuid4()
    transcript_row = SimpleNamespace(
        id=transcript_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        detected_language="en",
    )
    req = SimpleNamespace(transcript_id=transcript_id, source_language=None, target_language="es")

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == transcript_row.workspace_id
        assert kwargs["project_id"] == transcript_row.project_id
        assert kwargs["require_write"] is True
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(translation, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            translation.translate_project(
                req=req,
                request=_request(),
                context=context,
                db=FakeAsyncSession(transcript_row),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Transcript not found."


def test_tts_synthesize_segment_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    translation_id = uuid.uuid4()
    translation_row = SimpleNamespace(
        id=translation_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )
    req = SimpleNamespace(translation_id=translation_id)

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == translation_row.workspace_id
        assert kwargs["project_id"] == translation_row.project_id
        assert kwargs["require_write"] is True
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(tts, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            tts.synthesize_single_segment(
                req=req,
                request=_request(),
                context=context,
                db=FakeAsyncSession(translation_row),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Translation not found."


def test_lipsync_job_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    job_id = uuid.uuid4()
    job_row = SimpleNamespace(
        id=job_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        segments_metadata=[],
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == job_row.workspace_id
        assert kwargs["project_id"] == job_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(lipsync, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            lipsync.get_lipsync_job(
                job_id=job_id,
                context=context,
                db=FakeAsyncSession(job_row),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Lip-sync job not found."


def test_export_job_status_propagates_workspace_not_found(monkeypatch):
    context = _build_context()
    job_id = uuid.uuid4()
    job_row = SimpleNamespace(
        id=job_id,
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    )

    async def _deny(**kwargs):
        assert kwargs["workspace_id"] == job_row.workspace_id
        assert kwargs["project_id"] == job_row.project_id
        raise HTTPException(status_code=404, detail=kwargs["not_found_detail"])

    monkeypatch.setattr(export, "ensure_workspace_resource_access", _deny)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            export.get_export_job_status(
                job_id=job_id,
                context=context,
                db=FakeAsyncSession(job_row),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Export job not found."
