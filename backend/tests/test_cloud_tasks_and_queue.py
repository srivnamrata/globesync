import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.cloud_tasks_service import CloudTasksService
from app.services.export_queue_manager import ExportQueueManager
from app.services.pipeline_availability import require_background_pipelines
from app.utils.error_codes import ErrorCode, MediaAppException


def _configure_cloud_tasks(monkeypatch, *, enabled=True):
    values = {
        "CLOUD_TASKS_ENABLED": enabled,
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "CLOUD_TASKS_LOCATION": "us-central1",
        "CLOUD_TASKS_QUEUE": "pipeline",
        "CLOUD_TASKS_TARGET_URL": "https://api.example/",
        "CLOUD_TASKS_OIDC_SERVICE_ACCOUNT": "tasks@example.iam.gserviceaccount.com",
        "INTERNAL_TASKS_AUDIENCE": "https://api.example",
    }
    for name, value in values.items():
        monkeypatch.setattr(f"app.services.cloud_tasks_service.settings.{name}", value)


def _install_tasks_module(monkeypatch):
    import google.cloud

    tasks_v2 = SimpleNamespace(HttpMethod=SimpleNamespace(POST="POST"))
    monkeypatch.setitem(sys.modules, "google.cloud.tasks_v2", tasks_v2)
    monkeypatch.setattr(google.cloud, "tasks_v2", tasks_v2, raising=False)


def test_cloud_tasks_enabled_requires_every_security_setting(monkeypatch):
    _configure_cloud_tasks(monkeypatch)
    service = CloudTasksService()
    assert service.enabled is True

    monkeypatch.setattr(
        "app.services.cloud_tasks_service.settings.INTERNAL_TASKS_AUDIENCE",
        "",
    )
    assert service.enabled is False


def test_enqueue_http_task_builds_oidc_authenticated_idempotent_request(monkeypatch):
    _configure_cloud_tasks(monkeypatch)
    _install_tasks_module(monkeypatch)
    client = MagicMock()
    client.queue_path.return_value = "projects/test/locations/us/queues/pipeline"
    client.create_task.return_value = SimpleNamespace(name="tasks/generated")
    service = CloudTasksService()
    service._client = client

    name = service.enqueue_http_task(
        "/internal/transcribe",
        {"operation_id": "op-1", "attempt": 2},
        task_name_suffix="transcribe-op-1",
        dispatch_deadline_seconds=90,
    )

    assert name == "tasks/generated"
    request = client.create_task.call_args.kwargs["request"]
    assert request["parent"] == "projects/test/locations/us/queues/pipeline"
    task = request["task"]
    assert task["name"].endswith("/tasks/transcribe-op-1")
    assert task["dispatch_deadline"].seconds == 90
    http_request = task["http_request"]
    assert http_request["url"] == "https://api.example/internal/transcribe"
    assert json.loads(http_request["body"]) == {"operation_id": "op-1", "attempt": 2}
    assert http_request["headers"] == {"Content-Type": "application/json"}
    assert http_request["oidc_token"] == {
        "service_account_email": "tasks@example.iam.gserviceaccount.com",
        "audience": "https://api.example",
    }


def test_enqueue_http_task_requires_configuration(monkeypatch):
    _configure_cloud_tasks(monkeypatch, enabled=False)

    with pytest.raises(MediaAppException) as error:
        CloudTasksService().enqueue_http_task("/internal/task", {})

    assert error.value.status_code == 503
    assert error.value.error_code == ErrorCode.INTERNAL_SERVER_ERROR


def test_enqueue_http_task_treats_named_duplicate_as_success(monkeypatch):
    _configure_cloud_tasks(monkeypatch)
    _install_tasks_module(monkeypatch)

    class AlreadyExists(Exception):
        pass

    client = MagicMock()
    client.queue_path.return_value = "queues/pipeline"
    client.create_task.side_effect = AlreadyExists("duplicate")
    service = CloudTasksService()
    service._client = client

    assert (
        service.enqueue_http_task(
            "/internal/task",
            {"id": 1},
            task_name_suffix="stable-name",
        )
        == "queues/pipeline/tasks/stable-name"
    )


def test_enqueue_http_task_wraps_provider_failure(monkeypatch):
    _configure_cloud_tasks(monkeypatch)
    _install_tasks_module(monkeypatch)
    client = MagicMock()
    client.queue_path.return_value = "queues/pipeline"
    client.create_task.side_effect = RuntimeError("quota exhausted")
    service = CloudTasksService()
    service._client = client

    with pytest.raises(MediaAppException) as error:
        service.enqueue_http_task("/internal/task", {"id": 1})

    assert error.value.status_code == 502
    assert "quota exhausted" in error.value.message


def test_export_queue_lifecycle_uses_stable_cancel_key(monkeypatch):
    redis_client = MagicMock()
    redis_client.exists.return_value = 1
    monkeypatch.setattr(
        "app.services.export_queue_manager.settings.REDIS_URL",
        "redis://test",
    )

    with patch(
        "app.services.export_queue_manager.redis.Redis.from_url",
        return_value=redis_client,
    ):
        manager = ExportQueueManager()

    manager.register_job("job-1")
    assert manager.cancel_job("job-1") is True
    assert manager.is_cancelled("job-1") is True

    redis_client.rpush.assert_called_once_with("active_export_jobs_list", "job-1")
    redis_client.set.assert_called_once_with("cancel_flag_job:job-1", "true", ex=3600)
    redis_client.lrem.assert_called_once_with("active_export_jobs_list", 0, "job-1")


def test_export_queue_contains_redis_failures(monkeypatch):
    redis_client = MagicMock()
    redis_client.rpush.side_effect = RuntimeError("down")
    redis_client.lrem.side_effect = RuntimeError("down")
    redis_client.set.side_effect = RuntimeError("down")
    redis_client.exists.side_effect = RuntimeError("down")
    monkeypatch.setattr(
        "app.services.export_queue_manager.settings.REDIS_URL",
        "redis://test",
    )

    with patch(
        "app.services.export_queue_manager.redis.Redis.from_url",
        return_value=redis_client,
    ):
        manager = ExportQueueManager()

    manager.register_job("job-1")
    manager.deregister_job("job-1")
    assert manager.cancel_job("job-1") is False
    assert manager.is_cancelled("job-1") is False


def test_export_queue_cleanup_removes_only_existing_files(tmp_path):
    first = tmp_path / "first.tmp"
    second = tmp_path / "second.tmp"
    first.write_text("one")
    second.write_text("two")

    with patch("app.services.export_queue_manager.os.remove", wraps=lambda path: None) as remove:
        ExportQueueManager.cleanup_temporary_files(
            [str(first), "", str(tmp_path / "missing"), str(second)]
        )

    assert [call.args[0] for call in remove.call_args_list] == [str(first), str(second)]


def test_export_queue_cleanup_continues_after_delete_error(tmp_path):
    first = tmp_path / "first.tmp"
    second = tmp_path / "second.tmp"
    first.write_text("one")
    second.write_text("two")

    with patch(
        "app.services.export_queue_manager.os.remove",
        side_effect=[PermissionError("locked"), None],
    ) as remove:
        ExportQueueManager.cleanup_temporary_files([str(first), str(second)])

    assert remove.call_count == 2


def test_background_pipeline_guard_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "app.services.pipeline_availability.settings.ENABLE_BACKGROUND_PIPELINES",
        False,
    )
    with pytest.raises(HTTPException) as error:
        require_background_pipelines()
    assert error.value.status_code == 503

    monkeypatch.setattr(
        "app.services.pipeline_availability.settings.ENABLE_BACKGROUND_PIPELINES",
        True,
    )
    assert require_background_pipelines() is None
