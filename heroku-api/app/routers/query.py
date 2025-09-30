"""
Main compliance query endpoints
3 endpoints: query, feedback, history
"""

import hashlib
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.connection import get_session
from app.database.models import User, QueryLog, QueryFeedback
from app.services.grok4_rag_service import ask_compliance
from app.models.exceptions import InvalidQueryException, RateLimitExceededException

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["queries"])

# Redis-based rate limiting for distributed systems
import redis.asyncio as aioredis
import os

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create Redis client for rate limiting"""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = await aioredis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=10,
        )
    return _redis_client


class QueryRequest(BaseModel):
    """Compliance query request"""
    query: str = Field(..., min_length=10, max_length=2000, description="Compliance question")
    user_id: str = Field(..., description="Discord user ID")
    session_id: Optional[str] = Field(None, description="Session ID for context")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """
        Ensure query is meaningful and properly formatted.

        Args:
            v: Query string to validate

        Returns:
            Stripped and validated query string

        Raises:
            ValueError: If query is empty or too short
        """
        if not v.strip():
            raise ValueError("Query cannot be empty")
        if len(v.strip().split()) < 3:
            raise ValueError("Query too short - please provide more detail")
        return v.strip()


class QueryResponse(BaseModel):
    """Compliance query response"""
    answer: str
    confidence: str
    confidence_score: float
    risk: str
    sources: List[dict]
    query_id: str
    response_time_ms: int


class FeedbackRequest(BaseModel):
    """Feedback submission"""
    query_id: str
    overall_rating: int = Field(..., ge=1, le=5, description="Overall rating 1-5")
    helpfulness_rating: int = Field(..., ge=1, le=5, description="Helpfulness rating 1-5")
    accuracy_rating: int = Field(..., ge=1, le=5, description="Accuracy rating 1-5")
    feedback_text: Optional[str] = Field(None, max_length=1000)
    follow_up_needed: bool = False
    escalated: bool = False


class QueryHistoryResponse(BaseModel):
    """Query history item"""
    query_id: str
    query_text: str
    answer: str
    confidence: str
    risk: str
    created_at: str
    has_feedback: bool


@router.post("/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Process a compliance query using Grok-4 + RAG.

    Flow:
    1. Rate limit check
    2. Get or create user
    3. Call Grok-4 with RAG
    4. Log query and response
    5. Return answer
    """
    start_time = datetime.utcnow()

    # 1. Rate limiting
    await _check_rate_limit(request.user_id)

    logger.info(
        "query.received",
        user_id=request.user_id,
        query_length=len(request.query),
    )

    # 2. Get or create user
    user = await _get_or_create_user(session, request.user_id)

    # 3. Check daily limit
    if user.queries_today >= user.daily_query_limit:
        raise RateLimitExceededException(
            message="Daily query limit exceeded",
            limit=user.daily_query_limit,
            retry_after=_seconds_until_midnight(),
        )

    # 4. Query deduplication check
    query_hash = hashlib.sha256(request.query.encode()).hexdigest()
    recent_duplicate = await session.execute(
        select(QueryLog)
        .where(QueryLog.user_id == user.id)
        .where(QueryLog.query_hash == query_hash)
        .where(QueryLog.created_at > datetime.utcnow() - timedelta(minutes=5))
        .limit(1)
    )
    duplicate = recent_duplicate.scalar_one_or_none()

    if duplicate:
        logger.info("query.duplicate_detected", query_id=str(duplicate.id))
        # Return cached response
        response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        return QueryResponse(
            answer=duplicate.response_text,
            confidence="high" if duplicate.confidence_score >= 0.85 else "medium" if duplicate.confidence_score >= 0.6 else "low",
            confidence_score=duplicate.confidence_score,
            risk=duplicate.risk_level,
            sources=duplicate.rag_sources,
            query_id=str(duplicate.id),
            response_time_ms=response_time_ms,
        )

    # 5. Call Grok-4 with RAG
    try:
        result = await ask_compliance(request.query, request.user_id)
    except Exception as e:
        logger.error("query.grok4_failed", error=str(e))
        raise

    # 6. Calculate response time
    response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    result["response_time_ms"] = response_time_ms

    # 7. Create query log
    query_log = QueryLog(
        user_id=user.id,
        query_text=request.query,
        query_hash=query_hash,
        response_text=result["answer"],
        confidence_score=result["confidence_score"],
        risk_level=result["risk"],
        model_used=result["model_used"],
        response_time_ms=response_time_ms,
        rag_chunks_used=len(result["sources"]),
        rag_sources=result["sources"],
        session_id=request.session_id,
        is_flagged=result["confidence_score"] < 0.5,  # Flag low confidence
    )

    session.add(query_log)

    # 8. Update user stats
    user.total_queries += 1
    user.queries_today += 1
    user.last_query_at = datetime.utcnow()

    await session.commit()
    await session.refresh(query_log)

    logger.info(
        "query.success",
        query_id=str(query_log.id),
        confidence=result["confidence"],
        response_time_ms=response_time_ms,
    )

    return QueryResponse(
        answer=result["answer"],
        confidence=result["confidence"],
        confidence_score=result["confidence_score"],
        risk=result["risk"],
        sources=result["sources"],
        query_id=str(query_log.id),
        response_time_ms=response_time_ms,
    )


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Submit feedback for a query response.
    """
    # 1. Get query log
    query_log = await session.get(QueryLog, UUID(request.query_id))
    if not query_log:
        raise HTTPException(status_code=404, detail="Query not found")

    # 2. Check if feedback already exists
    existing = await session.execute(
        select(QueryFeedback).where(QueryFeedback.query_id == query_log.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Feedback already submitted")

    # 3. Create feedback
    feedback = QueryFeedback(
        user_id=query_log.user_id,
        query_id=query_log.id,
        overall_rating=request.overall_rating,
        helpfulness_rating=request.helpfulness_rating,
        accuracy_rating=request.accuracy_rating,
        feedback_text=request.feedback_text,
        follow_up_needed=request.follow_up_needed,
        escalated=request.escalated,
        escalation_reason=request.feedback_text if request.escalated else None,
    )

    session.add(feedback)
    await session.commit()

    logger.info(
        "feedback.submitted",
        query_id=request.query_id,
        overall_rating=request.overall_rating,
        escalated=request.escalated,
    )

    return {"status": "success", "feedback_id": str(feedback.id)}


@router.get("/history/{user_id}", response_model=List[QueryHistoryResponse])
async def get_query_history(
    user_id: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """
    Get query history for a user.
    """
    # 1. Get user
    result = await session.execute(
        select(User).where(User.discord_id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return []

    # 2. Get queries with feedback status
    queries = await session.execute(
        select(QueryLog, func.count(QueryFeedback.id).label("has_feedback"))
        .outerjoin(QueryFeedback, QueryFeedback.query_id == QueryLog.id)
        .where(QueryLog.user_id == user.id)
        .group_by(QueryLog.id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )

    history = []
    for query_log, has_feedback in queries:
        confidence_level = (
            "high" if query_log.confidence_score >= 0.85
            else "medium" if query_log.confidence_score >= 0.6
            else "low"
        )

        history.append(QueryHistoryResponse(
            query_id=str(query_log.id),
            query_text=query_log.query_text,
            answer=query_log.response_text[:500],  # Truncate for list view
            confidence=confidence_level,
            risk=query_log.risk_level,
            created_at=query_log.created_at.isoformat(),
            has_feedback=has_feedback > 0,
        ))

    return history


async def _check_rate_limit(user_id: str):
    """
    Check rate limit (30 req/min per user) using Redis.

    Uses Redis INCR with TTL for distributed rate limiting across multiple instances.

    Args:
        user_id: User identifier for rate limiting

    Raises:
        RateLimitExceededException: If rate limit is exceeded
    """
    redis = await get_redis_client()
    key = f"rate_limit:{user_id}"

    # Increment counter
    count = await redis.incr(key)

    # Set TTL on first request
    if count == 1:
        await redis.expire(key, 60)  # 60 seconds window

    if count > 30:
        ttl = await redis.ttl(key)
        raise RateLimitExceededException(
            message="Rate limit exceeded (30 requests per minute)",
            limit=30,
            retry_after=ttl if ttl > 0 else 60,
        )


async def _get_or_create_user(session: AsyncSession, discord_id: str) -> User:
    """Get existing user or create new one"""
    result = await session.execute(
        select(User).where(User.discord_id == discord_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            discord_id=discord_id,
            discord_username=f"user_{discord_id}",
            discord_discriminator="0000",
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        logger.info("user.created", discord_id=discord_id, user_id=str(user.id))

    return user


def _seconds_until_midnight() -> int:
    """Calculate seconds until next midnight UTC"""
    now = datetime.utcnow()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return int((tomorrow - now).total_seconds())