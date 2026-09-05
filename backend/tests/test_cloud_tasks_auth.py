from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core import cloud_tasks_auth


@pytest.fixture
def production_task_settings(monkeypatch):
    monkeypatch.setattr(cloud_tasks_auth.settings, "DEPLOYMENT_ENV", "production")
    monkeypatch.setattr(cloud_tasks_auth.settings, "CLOUD_TASKS_ENABLED", True)
    monkeypatch.setattr(
        cloud_tasks_auth.settings,
        "CLOUD_TASKS_OIDC_SERVICE_ACCOUNT",
        "globesync@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(cloud_tasks_auth.settings, "INTERNAL_TASKS_AUDIENCE", "https://api.example.com")
    monkeypatch.setattr(cloud_tasks_auth.settings, "CLOUD_TASKS_TARGET_URL", "https://api.example.com")


@pytest.mark.asyncio
async def test_rejects_forged_cloud_tasks_header_without_oidc(production_task_settings):
    with pytest.raises(HTTPException) as exc_info:
        await cloud_tasks_auth.verify_cloud_tasks_request(
            x_cloudtasks_taskname="forged-task",
            authorization=None,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_rejects_oidc_without_cloud_tasks_header(production_task_settings):
    with pytest.raises(HTTPException) as exc_info:
        await cloud_tasks_auth.verify_cloud_tasks_request(
            x_cloudtasks_taskname=None,
            authorization="******",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_rejects_oidc_when_server_auth_is_not_configured(
    production_task_settings,
    monkeypatch,
):
    monkeypatch.setattr(cloud_tasks_auth.settings, "CLOUD_TASKS_OIDC_SERVICE_ACCOUNT", None)

    with pytest.raises(HTTPException) as exc_info:
        await cloud_tasks_auth.verify_cloud_tasks_request(
            x_cloudtasks_taskname="projects/p/locations/l/queues/q/tasks/t",
            authorization="******",
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_rejects_invalid_oidc_token(production_task_settings, monkeypatch):
    verifier = MagicMock(side_effect=ValueError("invalid token"))
    monkeypatch.setattr(cloud_tasks_auth.id_token, "verify_oauth2_token", verifier)

    with pytest.raises(HTTPException) as exc_info:
        await cloud_tasks_auth.verify_cloud_tasks_request(
            x_cloudtasks_taskname="projects/p/locations/l/queues/q/tasks/t",
            authorization="Bearer " + "invalid",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unable to verify Cloud Tasks identity token."
    verifier.assert_called_once()


@pytest.mark.asyncio
async def test_rejects_oidc_token_from_another_service_account(
    production_task_settings,
    monkeypatch,
):
    monkeypatch.setattr(
        cloud_tasks_auth.id_token,
        "verify_oauth2_token",
        lambda *args, **kwargs: {
            "email": "attacker@example.iam.gserviceaccount.com",
            "email_verified": True,
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await cloud_tasks_auth.verify_cloud_tasks_request(
            x_cloudtasks_taskname="projects/p/locations/l/queues/q/tasks/t",
            authorization="Bearer valid-token",
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_accepts_oidc_token_from_configured_service_account(
    production_task_settings,
    monkeypatch,
):
    captured = SimpleNamespace(audience=None)

    def _verify(token, request, audience):
        captured.audience = audience
        return {
            "email": "globesync@example.iam.gserviceaccount.com",
            "email_verified": True,
        }

    monkeypatch.setattr(cloud_tasks_auth.id_token, "verify_oauth2_token", _verify)

    await cloud_tasks_auth.verify_cloud_tasks_request(
        x_cloudtasks_taskname="projects/p/locations/l/queues/q/tasks/t",
        authorization="Bearer valid-token",
    )

    assert captured.audience == "https://api.example.com"
