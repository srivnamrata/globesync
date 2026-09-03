import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import require_workspace_write_context
from app.core.database import get_db
from app.models.pipeline_operation import PipelineOperation
from app.models.project import Project
from app.models.transcript import Transcript
from app.routers.translation import router


WORKSPACE_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()
TRANSCRIPT_ID = uuid.uuid4()


class FakeAsyncSession:
    def __init__(self, operation, transcript, project):
        self.operation = operation
        self.transcript = transcript
        self.project = project
        self.added = []

    async def scalar(self, _statement):
        return self.operation

    async def get(self, model, _identifier):
        if model is Transcript:
            return self.transcript
        if model is Project:
            return self.project
        return None

    def add(self, entity):
        self.added.append(entity)

    async def flush(self):
        for entity in self.added:
            if isinstance(entity, PipelineOperation) and entity.id is None:
                entity.id = uuid.uuid4()

    async def commit(self):
        return None

    async def refresh(self, _entity):
        return None


def _build_app(session, enqueue):
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    context = SimpleNamespace(workspace_id=WORKSPACE_ID, user_id=uuid.uuid4(), membership_role="editor")

    async def _context():
        return context

    async def _db():
        yield session

    app.dependency_overrides[require_workspace_write_context] = _context
    app.dependency_overrides[get_db] = _db
    enqueue.enabled = True
    enqueue.enqueue_http_task = MagicMock(return_value="tasks/retry")
    return app, enqueue


@pytest.mark.parametrize("status", ["queued", "in_progress", "completed"])
def test_retry_rejects_non_failed_operation(monkeypatch, status):
    operation = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        transcript_id=TRANSCRIPT_ID,
        operation_type="translation",
        target_language="es",
        status=status,
        idempotency_key="translate:original",
    )
    session = FakeAsyncSession(operation, SimpleNamespace(detected_language="en"), SimpleNamespace(id=PROJECT_ID))
    from app.routers import translation

    monkeypatch.setattr(translation, "cloud_tasks_service", SimpleNamespace(enabled=True, enqueue_http_task=MagicMock()))
    app, _ = _build_app(session, translation.cloud_tasks_service)

    with TestClient(app) as client:
        response = client.post(f"/v1/translation/pipeline-operation/{operation.id}/retry")

    assert response.status_code == 409
    assert session.added == []


def test_retry_creates_new_operation_and_dispatches(monkeypatch):
    operation = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        transcript_id=TRANSCRIPT_ID,
        operation_type="translation",
        target_language="es",
        status="failed",
        idempotency_key="translate:original",
    )
    session = FakeAsyncSession(operation, SimpleNamespace(detected_language="fr"), SimpleNamespace(id=PROJECT_ID))
    from app.routers import translation

    cloud_tasks = SimpleNamespace(enabled=True, enqueue_http_task=MagicMock(return_value="tasks/retry"))
    monkeypatch.setattr(translation, "cloud_tasks_service", cloud_tasks)
    app, _ = _build_app(session, cloud_tasks)

    with TestClient(app) as client:
        response = client.post(
            f"/v1/translation/pipeline-operation/{operation.id}/retry",
            headers={"X-Request-ID": "retry-request"},
        )

    assert response.status_code == 202
    retry_operation = session.added[0]
    assert retry_operation.id != operation.id
    assert retry_operation.idempotency_key.startswith("translate:original:retry:")
    assert retry_operation.request_id == "retry-request"
    payload = cloud_tasks.enqueue_http_task.call_args.kwargs["payload"]
    assert payload["source_language"] == "fr"
    assert payload["operation_id"] == str(retry_operation.id)