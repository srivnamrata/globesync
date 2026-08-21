"""Guards for pipelines that require a dedicated asynchronous worker."""

from fastapi import HTTPException, status

from app.core.config import settings


def require_background_pipelines() -> None:
    """Fail clearly rather than accepting work that no deployed worker can run."""
    if not settings.ENABLE_BACKGROUND_PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Background media pipelines are unavailable in the two-service deployment. "
                "Deploy the worker/Cloud Run Job integration before starting this operation."
            ),
        )
