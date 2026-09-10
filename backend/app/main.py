import inspect
import time
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import app.models
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import ARRAY, String, bindparam, text

from app.core.config import settings
from app.core.database import Base, async_engine
from app.routers import auth, export, internal_tasks, lipsync, projects, transcription, translation, tts, upload
from app.utils.error_codes import ErrorCode, MediaAppException


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Schema migrations are applied as a deployment step, not by every Cloud
    Run instance at startup. This prevents DDL races during horizontal scale.
    """
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.2.0",
    description="Enterprise Audio & Video Translation, Voice Dubbing, and Lip-Sync API Platform.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Content-Range"],
)


# Global Middleware: Request ID and Performance Tracking
@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.time()
    
    # Store request_id in request state
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response


# Global Exception Handler for MediaAppException
@app.exception_handler(MediaAppException)
async def media_app_exception_handler(request: Request, exc: MediaAppException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code.value,
            "message": exc.message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "details": exc.details,
        },
    )


# General Exception Handler fallback
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": ErrorCode.INTERNAL_SERVER_ERROR.value,
            "message": "An unexpected server error occurred.",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "details": {"error": str(exc)} if settings.DEBUG else {},
        },
    )


# Liveness probe — no dependency checks
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "1.2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _expected_table_names() -> list[str]:
    return sorted(table.name for table in Base.metadata.sorted_tables)


# Readiness probe — only dependencies required to accept traffic
@app.get("/healthz", tags=["Health"])
async def readiness_check():
    try:
        readiness_query = text(
            """
            WITH alembic_version_check AS (
                SELECT version_num
                FROM alembic_version
                LIMIT 1
            ),
            expected_tables AS (
                SELECT unnest(:expected_tables) AS table_name
            ),
            missing_table_privileges AS (
                SELECT COALESCE(array_agg(table_name ORDER BY table_name), ARRAY[]::text[]) AS names
                FROM expected_tables
                WHERE NOT has_table_privilege(
                    current_user,
                    format('public.%I', table_name),
                    'SELECT,INSERT,UPDATE,DELETE'
                )
            ),
            missing_sequence_privileges AS (
                SELECT COALESCE(array_agg(sequence_name ORDER BY sequence_name), ARRAY[]::text[]) AS names
                FROM information_schema.sequences
                WHERE sequence_schema = 'public'
                  AND NOT has_sequence_privilege(
                      current_user,
                      format('%I.%I', sequence_schema, sequence_name),
                      'USAGE,SELECT,UPDATE'
                  )
            )
            SELECT
                EXISTS (SELECT 1 FROM alembic_version_check) AS alembic_version_ok,
                (SELECT names FROM missing_table_privileges) AS missing_table_privileges,
                (SELECT names FROM missing_sequence_privileges) AS missing_sequence_privileges
            """
        ).bindparams(bindparam("expected_tables", type_=ARRAY(String())))

        missing_table_privileges: list[str] = []
        missing_sequence_privileges: list[str] = []
        alembic_version_ok = True

        async with async_engine.connect() as conn:
            result = await conn.execute(
                readiness_query,
                {"expected_tables": _expected_table_names()},
            )

        row = None
        one = getattr(result, "one", None)
        if callable(one) and not isinstance(one, AsyncMock) and not inspect.iscoroutinefunction(one):
            row = one()

        if row is not None:
            mapping = getattr(row, "_mapping", row)
            alembic_version_ok = bool(mapping["alembic_version_ok"])
            missing_table_privileges = list(mapping["missing_table_privileges"] or [])
            missing_sequence_privileges = list(mapping["missing_sequence_privileges"] or [])

        if (not alembic_version_ok) or missing_table_privileges or missing_sequence_privileges:
            checks = {
                "database": "failed",
                "alembic_version": "ok" if alembic_version_ok else "failed",
                "table_privileges": "ok" if not missing_table_privileges else "failed",
                "sequence_privileges": "ok" if not missing_sequence_privileges else "failed",
            }
            detail = {
                "missing_table_privileges": missing_table_privileges,
                "missing_sequence_privileges": missing_sequence_privileges,
            }
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "checks": checks,
                    "detail": detail if settings.DEBUG else "database access incomplete",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            )

        return {
            "status": "ready",
            "checks": {
                "database": "ok",
                "alembic_version": "ok",
                "table_privileges": "ok",
                "sequence_privileges": "ok",
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "checks": {
                    "database": "failed",
                    "alembic_version": "failed",
                    "table_privileges": "unknown",
                    "sequence_privileges": "unknown",
                },
                "detail": str(exc) if settings.DEBUG else "database unavailable",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )


def mount_api_routers(api_app: FastAPI) -> None:
    api_app.include_router(auth.router, prefix=settings.API_V1_STR)
    api_app.include_router(upload.router, prefix=settings.API_V1_STR)
    api_app.include_router(transcription.router, prefix=settings.API_V1_STR)
    api_app.include_router(translation.router, prefix=settings.API_V1_STR)
    api_app.include_router(tts.router, prefix=settings.API_V1_STR)
    api_app.include_router(lipsync.router, prefix=settings.API_V1_STR)
    api_app.include_router(projects.router, prefix=settings.API_V1_STR)
    api_app.include_router(export.router, prefix=settings.API_V1_STR)
    api_app.include_router(internal_tasks.router, prefix=settings.API_V1_STR)


# Mount API Routers
mount_api_routers(app)