"""API routers package"""

from app.routers.health import router as health_router
from app.routers.query import router as query_router
from app.routers.admin import router as admin_router

__all__ = ["health_router", "query_router", "admin_router"]