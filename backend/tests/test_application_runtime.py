from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Response
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.requests import Request

from app import main
from app.core.auth import get_request_context
from app.core.config import Settings
from app.utils.error_codes import ErrorCode, MediaAppException


def _request(headers=None):
    encoded = [
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": encoded,
            "query_string": b"",
        }
    )


async def _dummy_request_context():
    runtime_user_id = "00000000-0000-0000-0000-000000000001"
    runtime_workspace_id = "00000000-0000-0000-0000-000000000002"

    return SimpleNamespace(
        user_id=runtime_user_id,
        workspace_id=runtime_workspace_id,
        bootstrap={
            "user": {
                "id": runtime_user_id,
                "email": "runtime@globesync.test",
                "display_name": "Runtime Test User",
                "auth_provider": "test",
                "auth_subject": "runtime-user-1",
                "is_active": True,
                "last_login_at": "2026-09-01T00:00:00Z",
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
            },
            "workspace": {
                "id": runtime_workspace_id,
                "name": "Runtime Test Workspace",
                "slug": "runtime-test-workspace",
                "owner_user_id": runtime_user_id,
                "is_personal": False,
                "archived_at": None,
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
            },
            "membership": {
                "workspace_id": runtime_workspace_id,
                "user_id": runtime_user_id,
                "role": "owner",
                "invited_by_user_id": None,
                "joined_at": "2026-09-01T00:00:00Z",
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
            },
            "bootstrap_completed": True,
        },
    )


def test_translation_provider_defaults_to_google():
    assert Settings.model_fields["TRANSLATION_PROVIDER"].default == "google"


def test_settings_allow_development_defaults():
    settings = Settings(DEPLOYMENT_ENV="development")

    assert settings.JWT_SECRET_KEY == "replace-with-super-secret-hex-key-in-production"


def test_settings_reject_production_placeholder_secrets():
    with pytest.raises(ValidationError) as error:
        Settings(DEPLOYMENT_ENV="production")

    assert "JWT_SECRET_KEY" in str(error.value)
    assert "DATABASE_URL" in str(error.value)


@pytest.mark.asyncio
async def test_lifespan_disposes_database_engine():
    dispose = AsyncMock()
    with patch.object(main, "async_engine", SimpleNamespace(dispose=dispose)):
        async with main.lifespan(main.app):
            dispose.assert_not_awaited()
        dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_middleware_preserves_client_request_id_and_adds_timing():
    request = _request({"X-Request-ID": "request-123"})

    async def call_next(received):
        assert received.state.request_id == "request-123"
        return Response(status_code=204)

    with patch.object(main.time, "time", side_effect=[10.0, 10.125]):
        response = await main.add_request_id_and_timing(request, call_next)

    assert response.headers["X-Request-ID"] == "request-123"
    assert response.headers["X-Process-Time"] == "0.1250s"


@pytest.mark.asyncio
async def test_media_exception_handler_returns_structured_safe_error():
    request = _request()
    request.state.request_id = "request-1"
    exception = MediaAppException(
        status_code=400,
        error_code=ErrorCode.INVALID_FORMAT,
        message="bad media",
        details={"field": "file"},
    )

    response = await main.media_app_exception_handler(request, exception)

    assert response.status_code == 400
    assert b'"error_code":"INVALID_FORMAT"' in response.body
    assert b'"request_id":"request-1"' in response.body
    assert b'"field":"file"' in response.body


@pytest.mark.asyncio
async def test_general_exception_handler_redacts_details_outside_debug(monkeypatch):
    request = _request()
    request.state.request_id = "request-2"
    monkeypatch.setattr(main.settings, "DEBUG", False)

    response = await main.general_exception_handler(request, RuntimeError("secret"))

    assert response.status_code == 500
    assert b'"details":{}' in response.body
    assert b"secret" not in response.body


@pytest.mark.asyncio
async def test_general_exception_handler_includes_debug_details(monkeypatch):
    request = _request()
    monkeypatch.setattr(main.settings, "DEBUG", True)

    response = await main.general_exception_handler(request, RuntimeError("diagnostic"))

    assert b'"error":"diagnostic"' in response.body


class _Connection:
    def __init__(self, error=None):
        self.error = error
        self.execute = AsyncMock()

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_readiness_checks_database_dependency():
    connection = _Connection()
    engine = SimpleNamespace(connect=lambda: connection)

    with patch.object(main, "async_engine", engine):
        result = await main.readiness_check()

    assert result["status"] == "ready"
    connection.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_failure_redacts_database_error(monkeypatch):
    monkeypatch.setattr(main.settings, "DEBUG", False)
    engine = SimpleNamespace(
        connect=lambda: _Connection(RuntimeError("database password leaked"))
    )

    with patch.object(main, "async_engine", engine):
        response = await main.readiness_check()

    assert response.status_code == 503
    assert b'"detail":"database unavailable"' in response.body
    assert b"password" not in response.body


def test_export_router_is_mounted_under_v1_prefix():
    expected_router_endpoints = [
        (main.auth.router, "/auth/bootstrap"),
        (main.upload.router, "/media/uploads/direct"),
        (main.transcription.router, "/transcription/start"),
        (main.translation.router, "/translation/translate-project"),
        (main.tts.router, "/tts/synthesize-project"),
        (main.lipsync.router, "/lipsync/render-project"),
        (main.projects.router, "/projects"),
        (main.export.router, "/export/render"),
        (main.internal_tasks.router, "/internal/tasks/transcribe"),
    ]

    for router, expected_path in expected_router_endpoints:
        router_paths = {
            f"{router.prefix}{route.path}"
            for route in router.routes
            if getattr(route, "path", None) is not None
        }
        assert expected_path in router_paths

    api_app = SimpleNamespace(include_router=Mock())
    main.mount_api_routers(api_app)

    for router, _ in expected_router_endpoints:
        api_app.include_router.assert_any_call(
            router,
            prefix=main.settings.API_V1_STR,
        )


@pytest.mark.asyncio
async def test_mounted_app_bootstrap_route_uses_global_middleware():
    main.app.dependency_overrides[get_request_context] = _dummy_request_context
    try:
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/auth/bootstrap", headers={"X-Request-ID": "runtime-request-1"})
    finally:
        main.app.dependency_overrides.pop(get_request_context, None)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "runtime-request-1"
    assert response.json()["workspace"]["id"] == "00000000-0000-0000-0000-000000000002"


@pytest.mark.asyncio
async def test_mounted_app_supported_languages_route_returns_expected_payload():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/translation/languages", headers={"X-Request-ID": "runtime-request-2"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "runtime-request-2"
    payload = response.json()
    assert "languages" in payload
    assert any(language["code"] == "en" for language in payload["languages"])
    assert any(language["code"] == "es" for language in payload["languages"])


@pytest.mark.asyncio
async def test_health_response_identifies_service():
    response = await main.health_check()

    assert response["status"] == "healthy"
    assert response["service"] == main.settings.PROJECT_NAME
    assert response["version"] == "1.2.0"
