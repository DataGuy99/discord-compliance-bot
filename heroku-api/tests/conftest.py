"""
Pytest configuration and fixtures for testing
"""

import pytest
import os
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/discord_bot_test"
os.environ["ADMIN_TOKEN"] = "test-admin-token-secure"
os.environ["XAI_API_KEY"] = "test-xai-key"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session"""
    from app.database.connection import async_session_factory

    async with async_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing"""
    from main import app

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac