from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedRequestContext, get_request_context
from app.schemas.auth import AuthBootstrapResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/bootstrap",
    response_model=AuthBootstrapResponse,
    summary="Bootstrap Authenticated User Context",
)
async def bootstrap_authenticated_context(
    context: AuthenticatedRequestContext = Depends(get_request_context),
):
    return context.bootstrap


@router.get(
    "/me",
    response_model=AuthBootstrapResponse,
    summary="Get Current Authenticated Context",
)
async def get_authenticated_context(
    context: AuthenticatedRequestContext = Depends(get_request_context),
):
    return context.bootstrap
