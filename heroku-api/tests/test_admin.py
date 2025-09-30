"""
Tests for admin endpoints
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_stats_requires_auth(client: AsyncClient):
    """Test admin stats endpoint requires authentication"""
    response = await client.get("/admin/stats")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_with_valid_token(client: AsyncClient):
    """Test admin stats with valid token"""
    headers = {"X-Admin-Token": "test-admin-token-secure"}
    response = await client.get("/admin/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_users" in data
    assert "total_queries" in data


@pytest.mark.asyncio
async def test_admin_stats_with_invalid_token(client: AsyncClient):
    """Test admin stats rejects invalid token"""
    headers = {"X-Admin-Token": "wrong-token"}
    response = await client.get("/admin/stats", headers=headers)
    assert response.status_code == 403