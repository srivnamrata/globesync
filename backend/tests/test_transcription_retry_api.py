import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.routers import transcription


WORKSPACE_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()
MEDIA_ID = uuid.uuid4()
TRANSCRIPT_ID = uuid.uuid4()


class FakeSession:
    def __init__(self, operation):
        self.operation = operation
        self.added = []

    async def scalar(self, _statement):
        return self.operation

    async def get(self, model, _identifier):
        if model.__name__ == "Transcript":
            return SimpleNamespace(detected_language="de")
        if model.__name__ == "Project":
            return SimpleNamespace(id=PROJECT_ID)
        return None

    def add(self, entity):
        self.added.append(entity)

    async def flush(self):
        for entity in self.added:
            entity.id = entity.id or uuid.uuid4()

    async def commit(self):
        return None

    async def refresh(self, _entity):
        return None


def operation(**overrides):
    values = {
        "id": uuid.uuid4(),
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "media_file_id": MEDIA_ID,
        "transcript_id": TRANSCRIPT_ID,
        "operation_type": "transcription",
        "status": "failed",
        "idempotency_key": "transcribe:original",
        "transcription_language": "de",
        "max_speakers": 3,
        "enable_noise_reduction": False,
        "enable_loudness_norm": True,
        "enable_vad": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_transcription_retry_rejects_legacy_operation_without_options(monkeypatch):
    old_operation = operation(enable_vad=None)
    session = FakeSession(old_operation)
    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", AsyncMockNoop())

    with pytest.raises(HTTPException) as exc_info:
        await transcription.retry_transcription_operation(
            request=SimpleNamespace(headers={}),
            operation_id=old_operation.id,
            context=SimpleNamespace(workspace_id=WORKSPACE_ID, membership_role="editor"),
            db=session,
        )

    assert exc_info.value.status_code == 409
    assert session.added == []


@pytest.mark.asyncio
async def test_transcription_retry_dispatches_stored_options(monkeypatch):
    old_operation = operation()
    session = FakeSession(old_operation)
    cloud_tasks = SimpleNamespace(enabled=True, enqueue_http_task=MagicMock())
    monkeypatch.setattr(transcription, "cloud_tasks_service", cloud_tasks)
    monkeypatch.setattr(transcription, "ensure_workspace_resource_access", AsyncMockNoop())

    response = await transcription.retry_transcription_operation(
        request=SimpleNamespace(headers={"X-Request-ID": "retry-request"}),
        operation_id=old_operation.id,
        context=SimpleNamespace(workspace_id=WORKSPACE_ID, membership_role="editor"),
        db=session,
    )

    assert response.status == "queued"
    payload = cloud_tasks.enqueue_http_task.call_args.kwargs["payload"]
    assert payload["language"] == "de"
    assert payload["max_speakers"] == 3
    assert payload["enable_noise_reduction"] is False
    assert payload["enable_loudness_norm"] is True
    assert payload["enable_vad"] is False
    assert payload["operation_id"] == payload["job_id"]


class AsyncMockNoop:
    async def __call__(self, **_kwargs):
        return None
