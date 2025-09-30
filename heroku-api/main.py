"""
FastAPI main application for Discord S&P Compliance Bot
Heroku-ready with Grok-4 + RAG integration
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import structlog
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.routers import health_router, query_router, admin_router
from app.models.exceptions import (
    ComplianceAPIException,
    ModelNotAvailableException,
    InvalidQueryException,
    InsufficientPermissionsException,
    RateLimitExceededException,
    ExternalAPIException,
    ComplianceProcessingException,
)
from app.database.connection import engine

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://discord.com").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# OpenTelemetry setup for observability
if ENVIRONMENT == "production":
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    logger.info(
        "app.startup",
        environment=ENVIRONMENT,
        python_version=os.sys.version.split()[0],
    )

    # Test database connection
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        logger.info("app.database.connected")
    except Exception as e:
        logger.error("app.database.connection_failed", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("app.shutdown")
    await engine.dispose()


# Create FastAPI application
app = FastAPI(
    title="Discord S&P Compliance Bot API",
    description="AI-powered compliance assistant using Grok-4-latest with RAG",
    version="1.0.0",
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    max_age=3600,
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing"""
    start_time = datetime.utcnow()

    logger.info(
        "request.started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )

    response = await call_next(request)

    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

    logger.info(
        "request.completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    return response


# Exception handlers
@app.exception_handler(ModelNotAvailableException)
async def model_not_available_handler(request: Request, exc: ModelNotAvailableException):
    """Handle Grok-4 API unavailability"""
    logger.error(
        "exception.model_unavailable",
        path=request.url.path,
        message=exc.message,
        context=exc.context,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "model_unavailable",
            "message": exc.message,
            "context": exc.context,
        },
    )


@app.exception_handler(InvalidQueryException)
async def invalid_query_handler(request: Request, exc: InvalidQueryException):
    """Handle invalid query requests"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "invalid_query",
            "message": exc.message,
            "context": exc.context,
        },
    )


@app.exception_handler(InsufficientPermissionsException)
async def insufficient_permissions_handler(request: Request, exc: InsufficientPermissionsException):
    """Handle permission errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "insufficient_permissions",
            "message": exc.message,
            "required_permission": exc.context.get("required_permission"),
        },
    )


@app.exception_handler(RateLimitExceededException)
async def rate_limit_handler(request: Request, exc: RateLimitExceededException):
    """Handle rate limiting"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "rate_limit_exceeded",
            "message": exc.message,
            "limit": exc.context.get("limit"),
            "retry_after": exc.context.get("retry_after"),
        },
        headers={"Retry-After": str(exc.context.get("retry_after", 60))},
    )


@app.exception_handler(ExternalAPIException)
async def external_api_handler(request: Request, exc: ExternalAPIException):
    """Handle external API errors"""
    logger.error(
        "exception.external_api",
        path=request.url.path,
        service=exc.context.get("service"),
        error=exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "external_api_error",
            "message": exc.message,
            "service": exc.context.get("service"),
        },
    )


@app.exception_handler(ComplianceProcessingException)
async def compliance_processing_handler(request: Request, exc: ComplianceProcessingException):
    """Handle compliance processing errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "processing_error",
            "message": exc.message,
            "stage": exc.context.get("stage"),
        },
    )


@app.exception_handler(ComplianceAPIException)
async def generic_api_handler(request: Request, exc: ComplianceAPIException):
    """Handle generic API exceptions"""
    logger.error(
        "exception.api_error",
        path=request.url.path,
        message=exc.message,
        context=exc.context,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "api_error",
            "message": exc.message,
            "context": exc.context,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Invalid request data",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected exceptions"""
    logger.error(
        "exception.unexpected",
        path=request.url.path,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
        },
    )


# Include routers
app.include_router(health_router)
app.include_router(query_router)
app.include_router(admin_router)


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Discord S&P Compliance Bot API",
        "version": "1.0.0",
        "status": "operational",
        "documentation": "/docs" if ENVIRONMENT != "production" else None,
        "health_check": "/health",
        "environment": ENVIRONMENT,
    }


# OpenTelemetry instrumentation (production only)
if ENVIRONMENT == "production":
    FastAPIInstrumentor.instrument_app(app)
    logger.info("app.telemetry.enabled")


# Log startup configuration
logger.info(
    "app.configured",
    environment=ENVIRONMENT,
    cors_origins=CORS_ORIGINS,
    log_level=LOG_LEVEL,
)