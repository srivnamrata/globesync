from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Response
from starlette.requests import Request

from app import main
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


def test_translation_provider_defaults_to_google():
    assert Settings.model_fields["TRANSLATION_PROVIDER"].default == "google"


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


@pytest.mark.asyncio
async def test_health_response_identifies_service():
    response = await main.health_check()

    assert response["status"] == "healthy"
    assert response["service"] == main.settings.PROJECT_NAME
    assert response["version"] == "1.2.0"
