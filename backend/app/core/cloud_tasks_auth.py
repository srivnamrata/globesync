from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import Header, HTTPException, status
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from app.core.config import settings


async def verify_cloud_tasks_request(
    x_cloudtasks_taskname: Optional[str] = Header(None, alias="X-CloudTasks-TaskName"),
    authorization: Optional[str] = Header(None),
) -> None:
    """Verify that an internal pipeline request was signed by the task service account."""
    if settings.DEPLOYMENT_ENV == "development" and not settings.CLOUD_TASKS_ENABLED:
        return

    if not x_cloudtasks_taskname:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal task endpoints accept Cloud Tasks deliveries only.",
        )

    expected_service_account = (settings.CLOUD_TASKS_OIDC_SERVICE_ACCOUNT or "").strip().lower()
    expected_audience = (settings.INTERNAL_TASKS_AUDIENCE or settings.CLOUD_TASKS_TARGET_URL or "").strip()
    if not expected_service_account or not expected_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal task authentication is not configured.",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Cloud Tasks identity token.",
        )

    def _verify() -> dict:
        return id_token.verify_oauth2_token(
            token.strip(),
            GoogleAuthRequest(),
            expected_audience,
        )

    try:
        claims = await asyncio.to_thread(_verify)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to verify Cloud Tasks identity token.",
        ) from exc

    token_email = str(claims.get("email") or "").strip().lower()
    if token_email != expected_service_account or claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cloud Tasks identity is not authorized.",
        )
