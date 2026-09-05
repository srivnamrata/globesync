"""Cloud Tasks client for enqueueing short idempotent API jobs."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.utils.error_codes import ErrorCode, MediaAppException

logger = logging.getLogger("cloud_tasks_service")


class CloudTasksService:
    def __init__(self) -> None:
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(
            settings.CLOUD_TASKS_ENABLED
            and settings.GOOGLE_CLOUD_PROJECT
            and settings.CLOUD_TASKS_LOCATION
            and settings.CLOUD_TASKS_QUEUE
            and settings.CLOUD_TASKS_TARGET_URL
        )

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import tasks_v2
            except ImportError as exc:
                raise MediaAppException(
                    status_code=500,
                    error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                    message="google-cloud-tasks is not installed.",
                ) from exc
            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def enqueue_http_task(
        self,
        relative_handler_path: str,
        payload: Dict[str, Any],
        task_name_suffix: Optional[str] = None,
        dispatch_deadline_seconds: Optional[int] = None,
    ) -> str:
        """Creates an OIDC-authenticated HTTP task targeting the API service."""
        if not self.enabled:
            raise MediaAppException(
                status_code=503,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Cloud Tasks is not configured for this deployment.",
            )

        from google.cloud import tasks_v2
        from google.protobuf import duration_pb2, timestamp_pb2  # noqa: F401  # kept for future scheduleTime

        client = self._get_client()
        parent = client.queue_path(
            settings.GOOGLE_CLOUD_PROJECT,
            settings.CLOUD_TASKS_LOCATION,
            settings.CLOUD_TASKS_QUEUE,
        )
        target_url = settings.CLOUD_TASKS_TARGET_URL.rstrip("/") + relative_handler_path
        audience = settings.INTERNAL_TASKS_AUDIENCE or settings.CLOUD_TASKS_TARGET_URL

        http_request: Dict[str, Any] = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": target_url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload).encode("utf-8"),
        }
        if settings.CLOUD_TASKS_OIDC_SERVICE_ACCOUNT:
            http_request["oidc_token"] = {
                "service_account_email": settings.CLOUD_TASKS_OIDC_SERVICE_ACCOUNT,
                "audience": audience,
            }

        task: Dict[str, Any] = {"http_request": http_request}
        if dispatch_deadline_seconds is not None:
            task["dispatch_deadline"] = duration_pb2.Duration(seconds=dispatch_deadline_seconds)
        if task_name_suffix:
            task["name"] = f"{parent}/tasks/{task_name_suffix}"

        try:
            response = client.create_task(request={"parent": parent, "task": task})
            logger.info("Enqueued Cloud Task %s → %s", response.name, target_url)
            return response.name
        except Exception as exc:
            # Idempotent re-enqueue of the same task name is treated as success.
            if task_name_suffix and "AlreadyExists" in type(exc).__name__:
                return f"{parent}/tasks/{task_name_suffix}"
            logger.error("Failed to enqueue Cloud Task", exc_info=True)
            raise MediaAppException(
                status_code=502,
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message=f"Failed to enqueue Cloud Task: {exc}",
            ) from exc


cloud_tasks_service = CloudTasksService()
