"""
API client for communicating with FastAPI backend
"""

import os
from typing import Dict, Any, List, Optional

import httpx
from utils.logger import logger

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = 30.0


class APIClient:
    """
    HTTP client for Heroku API backend.
    Handles all communication between Discord bot and FastAPI.
    """

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=TIMEOUT,
            headers={"User-Agent": "DiscordComplianceBot/1.0"},
        )

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def health_check(self) -> Dict[str, Any]:
        """
        Check API health status.

        Returns:
            Health status dictionary
        """
        try:
            response = await self.client.get("/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("api.health_check.failed", error=str(e))
            return {"status": "unhealthy", "error": str(e)}

    async def submit_query(
        self,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit compliance query to API.

        Args:
            query: User's compliance question
            user_id: Discord user ID
            session_id: Optional session ID for context

        Returns:
            Query response with answer, confidence, risk, sources

        Raises:
            httpx.HTTPStatusError: If API returns error status
        """
        payload = {
            "query": query,
            "user_id": user_id,
            "session_id": session_id,
        }

        logger.info(
            "api.query.submit",
            user_id=user_id,
            query_length=len(query),
        )

        try:
            response = await self.client.post("/api/v1/query", json=payload)
            response.raise_for_status()
            data = response.json()

            logger.info(
                "api.query.success",
                query_id=data.get("query_id"),
                confidence=data.get("confidence"),
            )

            return data

        except httpx.HTTPStatusError as e:
            logger.error(
                "api.query.http_error",
                status_code=e.response.status_code,
                error=e.response.text,
            )
            raise

        except Exception as e:
            logger.error("api.query.failed", error=str(e))
            raise

    async def submit_feedback(
        self,
        query_id: str,
        overall_rating: int,
        helpfulness_rating: int,
        accuracy_rating: int,
        feedback_text: Optional[str] = None,
        follow_up_needed: bool = False,
        escalated: bool = False,
    ) -> Dict[str, Any]:
        """
        Submit feedback for a query response.

        Args:
            query_id: Query ID to provide feedback for
            overall_rating: Overall rating 1-5
            helpfulness_rating: Helpfulness rating 1-5
            accuracy_rating: Accuracy rating 1-5
            feedback_text: Optional feedback text
            follow_up_needed: Whether follow-up is needed
            escalated: Whether to escalate to human review

        Returns:
            Feedback submission confirmation
        """
        payload = {
            "query_id": query_id,
            "overall_rating": overall_rating,
            "helpfulness_rating": helpfulness_rating,
            "accuracy_rating": accuracy_rating,
            "feedback_text": feedback_text,
            "follow_up_needed": follow_up_needed,
            "escalated": escalated,
        }

        logger.info("api.feedback.submit", query_id=query_id, overall_rating=overall_rating)

        try:
            response = await self.client.post("/api/v1/feedback", json=payload)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "api.feedback.http_error",
                status_code=e.response.status_code,
                error=e.response.text,
            )
            raise

        except Exception as e:
            logger.error("api.feedback.failed", error=str(e))
            raise

    async def get_query_history(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get query history for a user.

        Args:
            user_id: Discord user ID
            limit: Maximum number of queries to return

        Returns:
            List of query history items
        """
        logger.info("api.history.get", user_id=user_id, limit=limit)

        try:
            response = await self.client.get(
                f"/api/v1/history/{user_id}",
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "api.history.http_error",
                status_code=e.response.status_code,
                error=e.response.text,
            )
            raise

        except Exception as e:
            logger.error("api.history.failed", error=str(e))
            raise

    async def get_admin_stats(self, admin_token: str) -> Dict[str, Any]:
        """
        Get system statistics (admin only).

        Args:
            admin_token: Admin authentication token

        Returns:
            System statistics
        """
        try:
            response = await self.client.get(
                "/admin/stats",
                headers={"X-Admin-Token": admin_token},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error("api.admin.stats.failed", error=str(e))
            raise

    async def get_flagged_queries(
        self,
        admin_token: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get flagged queries for review (admin only).

        Args:
            admin_token: Admin authentication token
            limit: Maximum number of queries to return

        Returns:
            List of flagged queries
        """
        try:
            response = await self.client.get(
                "/admin/queries/flagged",
                headers={"X-Admin-Token": admin_token},
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error("api.admin.flagged.failed", error=str(e))
            raise