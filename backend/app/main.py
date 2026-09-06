import time
import uuid
from contextlib import asynccontextmanager

import app.models
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, async_engine
from app.routers import auth, internal_tasks, lipsync, projects, transcription, translation, tts, upload
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
        expected_tables = _expected_table_names()
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))

            missing_table_privileges = []
            for table_name in expected_tables:
                result = await conn.execute(
                    text(
                        """
                        SELECT has_table_privilege(current_user, :table_name, 'SELECT,INSERT,UPDATE,DELETE')
                        """
                    ),
                    {"table_name": table_name},
                )
                if not result.scalar():
                    missing_table_privileges.append(table_name)

            sequence_result = await conn.execute(
                text(
                    """
                    SELECT sequence_name
                    FROM information_schema.sequences
                    WHERE sequence_schema = 'public'
                      AND NOT has_sequence_privilege(
                          current_user,
                          format('%I.%I', sequence_schema, sequence_name),
                          'USAGE,SELECT,UPDATE'
                      )
                    ORDER BY sequence_name
                    """
                )
            )
            missing_sequence_privileges = list(sequence_result.scalars())

        if missing_table_privileges or missing_sequence_privileges:
            checks = {
                "database": "failed",
                "alembic_version": "ok",
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


# Mount API Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(upload.router, prefix=settings.API_V1_STR)
app.include_router(transcription.router, prefix=settings.API_V1_STR)
app.include_router(translation.router, prefix=settings.API_V1_STR)
app.include_router(tts.router, prefix=settings.API_V1_STR)
app.include_router(lipsync.router, prefix=settings.API_V1_STR)
app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(internal_tasks.router, prefix=settings.API_V1_STR)