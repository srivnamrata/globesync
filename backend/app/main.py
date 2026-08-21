import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.core.database import async_engine
from app.routers import export, internal_tasks, lipsync, transcription, translation, tts, upload
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


# Readiness probe — only dependencies required to accept traffic
@app.get("/healthz", tags=["Health"])
async def readiness_check():
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "checks": {"database": "ok"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "checks": {"database": "failed"},
                "detail": str(exc) if settings.DEBUG else "database unavailable",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )


# Mount API Routers
app.include_router(upload.router, prefix=settings.API_V1_STR)
app.include_router(transcription.router, prefix=settings.API_V1_STR)
app.include_router(translation.router, prefix=settings.API_V1_STR)
app.include_router(tts.router, prefix=settings.API_V1_STR)
app.include_router(lipsync.router, prefix=settings.API_V1_STR)
app.include_router(export.router, prefix=settings.API_V1_STR)
app.include_router(internal_tasks.router, prefix=settings.API_V1_STR)
