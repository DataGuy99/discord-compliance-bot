"""
Health check endpoints for monitoring and observability
5 endpoints: basic, detailed, ready, live, metrics
"""

import os
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Response
from pydantic import BaseModel
import structlog
import psutil

from app.database.connection import engine
from app.services.grok4_rag_service import health_check as grok4_health
from app.rag.store import VectorStore

logger = structlog.get_logger()
router = APIRouter(prefix="/health", tags=["health"])

# Track startup time
_startup_time = time.time()


class HealthResponse(BaseModel):
    """Basic health response"""
    status: str
    timestamp: str
    uptime_seconds: float


class DetailedHealthResponse(BaseModel):
    """Detailed health response with component checks"""
    status: str
    timestamp: str
    uptime_seconds: float
    components: Dict[str, Any]
    system: Dict[str, Any]


@router.get("", response_model=HealthResponse)
async def health_basic():
    """
    Basic health check.
    Returns 200 if service is running.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - _startup_time,
    }


@router.get("/detailed", response_model=DetailedHealthResponse)
async def health_detailed():
    """
    Detailed health check with all components.
    Checks database, Grok-4, Redis, and system resources.
    """
    components = {}
    overall_status = "healthy"

    # 1. Database check
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        components["database"] = {
            "status": "healthy",
            "type": "postgresql",
        }
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # 2. Grok-4 API check
    try:
        grok4_available = await grok4_health()
        components["grok4"] = {
            "status": "healthy" if grok4_available else "unhealthy",
            "model": "grok-4-latest",
        }
        if not grok4_available:
            overall_status = "degraded"
    except Exception as e:
        components["grok4"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # 3. Redis vector store check
    try:
        vector_store = VectorStore()
        chunk_count = vector_store.count_chunks()
        vector_store.close()

        components["redis"] = {
            "status": "healthy",
            "chunks_stored": chunk_count,
        }
    except Exception as e:
        components["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        overall_status = "degraded"

    # 4. System resources
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        system_info = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available / (1024 * 1024),
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / (1024 * 1024 * 1024),
        }

        # Warn if resources are constrained
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            overall_status = "degraded"

    except Exception as e:
        system_info = {"error": str(e)}

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - _startup_time,
        "components": components,
        "system": system_info,
    }


@router.get("/ready")
async def health_ready(response: Response):
    """
    Kubernetes readiness probe.
    Returns 200 if ready to accept traffic, 503 otherwise.
    """
    # Check critical components
    try:
        # Database must be accessible
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")

        # Grok-4 should be available
        grok4_available = await grok4_health()
        if not grok4_available:
            response.status_code = 503
            return {"status": "not_ready", "reason": "grok4_unavailable"}

        return {"status": "ready"}

    except Exception as e:
        response.status_code = 503
        logger.error("health.ready.fail", error=str(e))
        return {"status": "not_ready", "reason": str(e)}


@router.get("/live")
async def health_live():
    """
    Kubernetes liveness probe.
    Returns 200 if process is alive (doesn't check dependencies).
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - _startup_time,
    }


@router.get("/metrics")
async def health_metrics():
    """
    Prometheus-style metrics endpoint.
    Returns application and system metrics.
    """
    try:
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Application metrics
        vector_store = VectorStore()
        chunk_count = vector_store.count_chunks()
        vector_store.close()

        metrics = {
            "system": {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_total_mb": memory.total / (1024 * 1024),
                "memory_used_mb": memory.used / (1024 * 1024),
                "disk_usage_percent": disk.percent,
                "disk_total_gb": disk.total / (1024 * 1024 * 1024),
                "disk_used_gb": disk.used / (1024 * 1024 * 1024),
            },
            "application": {
                "uptime_seconds": time.time() - _startup_time,
                "environment": os.getenv("ENVIRONMENT", "unknown"),
                "rag_chunks_stored": chunk_count,
                "python_version": os.sys.version.split()[0],
            },
        }

        return metrics

    except Exception as e:
        logger.error("health.metrics.fail", error=str(e))
        return {"error": str(e)}