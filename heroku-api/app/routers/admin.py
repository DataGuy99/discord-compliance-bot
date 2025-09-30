"""
Admin endpoints for system management
7 endpoints: stats, users, permissions, flagged queries, audit log, model retrain, GDPR deletion
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database.connection import get_session
from app.database.models import User, QueryLog, QueryFeedback, ComplianceDocument, SystemAuditLog
from app.models.exceptions import InsufficientPermissionsException
from app.rag.ingest import ingest_document

logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])

# Admin token from environment - MUST be set
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
if not ADMIN_TOKEN:
    logger.critical("admin.token_not_set")
    raise ValueError("ADMIN_TOKEN environment variable must be set for security")


async def verify_admin(x_admin_token: str = Header(...)) -> None:
    """
    Verify admin token from header using constant-time comparison.

    Args:
        x_admin_token: Admin token from X-Admin-Token header

    Raises:
        InsufficientPermissionsException: If token is invalid
    """
    import secrets

    if not secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        logger.warning("admin.unauthorized_access_attempt")
        raise InsufficientPermissionsException(
            message="Invalid admin token",
            required_permission="admin",
        )


class SystemStatsResponse(BaseModel):
    """System-wide statistics"""
    total_users: int
    active_users_7d: int
    total_queries: int
    queries_today: int
    avg_confidence_score: float
    total_feedback: int
    avg_overall_rating: float
    flagged_queries: int
    compliance_documents: int
    system_uptime_hours: float


class UserListItem(BaseModel):
    """User list item"""
    user_id: str
    discord_id: str
    discord_username: str
    role: str
    total_queries: int
    queries_today: int
    last_query_at: Optional[str]
    is_banned: bool
    created_at: str


class UserUpdateRequest(BaseModel):
    """Update user permissions"""
    role: Optional[str] = Field(None, description="User role: user, moderator, admin")
    daily_query_limit: Optional[int] = Field(None, ge=0, le=10000)
    is_banned: Optional[bool] = None
    ban_reason: Optional[str] = Field(None, max_length=500)


class FlaggedQueryResponse(BaseModel):
    """Flagged query for review"""
    query_id: str
    user_id: str
    discord_username: str
    query_text: str
    response_text: str
    confidence_score: float
    risk_level: str
    is_escalated: bool
    feedback_text: Optional[str]
    created_at: str


class AuditLogResponse(BaseModel):
    """Audit log entry"""
    log_id: str
    event_type: str
    actor_id: Optional[str]
    actor_username: Optional[str]
    target_resource: Optional[str]
    action_details: dict
    timestamp: str


class ModelRetrainRequest(BaseModel):
    """Model retraining trigger"""
    document_url: str = Field(..., description="URL to PDF compliance document")
    document_id: str = Field(..., description="Unique document identifier")
    document_title: str = Field(..., description="Document title")
    document_type: str = Field(..., description="Type: policy, guideline, regulation")
    force_reindex: bool = Field(False, description="Force reindex if already exists")


@router.get("/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    Get system-wide statistics and analytics.
    Requires admin token in X-Admin-Token header.
    """
    logger.info("admin.stats.requested")

    # Calculate 7 days ago
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    # 1. User statistics
    total_users_result = await session.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar()

    active_users_result = await session.execute(
        select(func.count(User.id)).where(User.last_query_at >= seven_days_ago)
    )
    active_users_7d = active_users_result.scalar() or 0

    # 2. Query statistics
    total_queries_result = await session.execute(select(func.count(QueryLog.id)))
    total_queries = total_queries_result.scalar() or 0

    queries_today_result = await session.execute(
        select(func.count(QueryLog.id)).where(
            QueryLog.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        )
    )
    queries_today = queries_today_result.scalar() or 0

    # 3. Average confidence
    avg_confidence_result = await session.execute(
        select(func.avg(QueryLog.confidence_score))
    )
    avg_confidence = avg_confidence_result.scalar() or 0.0

    # 4. Feedback statistics
    total_feedback_result = await session.execute(select(func.count(QueryFeedback.id)))
    total_feedback = total_feedback_result.scalar() or 0

    avg_rating_result = await session.execute(
        select(func.avg(QueryFeedback.overall_rating))
    )
    avg_rating = avg_rating_result.scalar() or 0.0

    # 5. Flagged queries
    flagged_result = await session.execute(
        select(func.count(QueryLog.id)).where(
            or_(
                QueryLog.is_flagged == True,
                QueryLog.confidence_score < 0.5,
            )
        )
    )
    flagged_queries = flagged_result.scalar() or 0

    # 6. Compliance documents
    docs_result = await session.execute(select(func.count(ComplianceDocument.id)))
    compliance_docs = docs_result.scalar() or 0

    # 7. System uptime (approximate from oldest audit log)
    oldest_log_result = await session.execute(
        select(SystemAuditLog.timestamp).order_by(SystemAuditLog.timestamp.asc()).limit(1)
    )
    oldest_log = oldest_log_result.scalar_one_or_none()
    uptime_hours = 0.0
    if oldest_log:
        uptime_hours = (datetime.utcnow() - oldest_log).total_seconds() / 3600

    return SystemStatsResponse(
        total_users=total_users,
        active_users_7d=active_users_7d,
        total_queries=total_queries,
        queries_today=queries_today,
        avg_confidence_score=round(avg_confidence, 3),
        total_feedback=total_feedback,
        avg_overall_rating=round(avg_rating, 2),
        flagged_queries=flagged_queries,
        compliance_documents=compliance_docs,
        system_uptime_hours=round(uptime_hours, 1),
    )


@router.get("/users", response_model=List[UserListItem])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    role: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    List all users with pagination and optional role filter.
    Requires admin token in X-Admin-Token header.
    """
    logger.info("admin.users.list", limit=limit, offset=offset, role=role)

    query = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)

    if role:
        query = query.where(User.role == role)

    result = await session.execute(query)
    users = result.scalars().all()

    user_list = []
    for user in users:
        user_list.append(UserListItem(
            user_id=str(user.id),
            discord_id=user.discord_id,
            discord_username=user.discord_username,
            role=user.role,
            total_queries=user.total_queries,
            queries_today=user.queries_today,
            last_query_at=user.last_query_at.isoformat() if user.last_query_at else None,
            is_banned=user.is_banned,
            created_at=user.created_at.isoformat(),
        ))

    return user_list


@router.put("/users/{user_id}")
async def update_user_permissions(
    user_id: str,
    request: UserUpdateRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    Update user role, permissions, and ban status.
    Requires admin token in X-Admin-Token header.
    """
    logger.info("admin.users.update", user_id=user_id, updates=request.dict(exclude_none=True))

    # Get user
    user = await session.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Apply updates
    updated_fields = []
    if request.role is not None:
        if request.role not in ["user", "moderator", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = request.role
        updated_fields.append(f"role={request.role}")

    if request.daily_query_limit is not None:
        user.daily_query_limit = request.daily_query_limit
        updated_fields.append(f"daily_query_limit={request.daily_query_limit}")

    if request.is_banned is not None:
        user.is_banned = request.is_banned
        updated_fields.append(f"is_banned={request.is_banned}")

        if request.is_banned and request.ban_reason:
            user.ban_reason = request.ban_reason
            user.banned_at = datetime.utcnow()
        elif not request.is_banned:
            user.ban_reason = None
            user.banned_at = None

    user.updated_at = datetime.utcnow()

    await session.commit()

    # Create audit log
    audit_log = SystemAuditLog(
        event_type="user_permissions_updated",
        actor_id=None,  # Admin action
        target_resource=f"user:{user_id}",
        action_details={
            "updates": updated_fields,
            "new_role": user.role,
            "is_banned": user.is_banned,
        },
    )
    session.add(audit_log)
    await session.commit()

    logger.info("admin.users.updated", user_id=user_id, changes=updated_fields)

    return {
        "status": "success",
        "user_id": str(user.id),
        "updated_fields": updated_fields,
    }


@router.get("/queries/flagged", response_model=List[FlaggedQueryResponse])
async def get_flagged_queries(
    limit: int = 50,
    include_escalated: bool = True,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    Get queries flagged for review (low confidence or escalated feedback).
    Requires admin token in X-Admin-Token header.
    """
    logger.info("admin.queries.flagged", limit=limit, include_escalated=include_escalated)

    # Build query for flagged queries
    query = (
        select(QueryLog, User, QueryFeedback)
        .join(User, User.id == QueryLog.user_id)
        .outerjoin(QueryFeedback, QueryFeedback.query_id == QueryLog.id)
        .where(
            or_(
                QueryLog.is_flagged == True,
                QueryLog.confidence_score < 0.5,
                and_(
                    QueryFeedback.escalated == True if include_escalated else False,
                )
            )
        )
        .order_by(desc(QueryLog.created_at))
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.all()

    flagged_list = []
    for query_log, user, feedback in rows:
        flagged_list.append(FlaggedQueryResponse(
            query_id=str(query_log.id),
            user_id=str(user.id),
            discord_username=user.discord_username,
            query_text=query_log.query_text,
            response_text=query_log.response_text[:1000],  # Truncate for admin view
            confidence_score=query_log.confidence_score,
            risk_level=query_log.risk_level,
            is_escalated=feedback.escalated if feedback else False,
            feedback_text=feedback.feedback_text if feedback else None,
            created_at=query_log.created_at.isoformat(),
        ))

    return flagged_list


@router.get("/audit-log", response_model=List[AuditLogResponse])
async def get_audit_log(
    limit: int = 100,
    event_type: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    Get system audit log with optional event type filter.
    Requires admin token in X-Admin-Token header.
    """
    from sqlalchemy.orm import selectinload

    logger.info("admin.audit_log.requested", limit=limit, event_type=event_type)

    # Use selectinload to prevent N+1 queries - eagerly load actor relationship
    query = (
        select(SystemAuditLog)
        .options(selectinload(SystemAuditLog.actor))
        .order_by(desc(SystemAuditLog.timestamp))
        .limit(limit)
    )

    if event_type:
        query = query.where(SystemAuditLog.event_type == event_type)

    result = await session.execute(query)
    logs = result.scalars().all()

    audit_list = []
    for log in logs:
        # Actor is now preloaded, no additional query needed
        actor_username = log.actor.discord_username if log.actor else None

        audit_list.append(AuditLogResponse(
            log_id=str(log.id),
            event_type=log.event_type,
            actor_id=str(log.actor_id) if log.actor_id else None,
            actor_username=actor_username,
            target_resource=log.target_resource,
            action_details=log.action_details,
            timestamp=log.timestamp.isoformat(),
        ))

    return audit_list


@router.post("/model/retrain")
async def trigger_model_retrain(
    request: ModelRetrainRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    Trigger model retraining by ingesting a new compliance document.
    Downloads PDF, extracts text, chunks it, embeds, and stores in Redis.
    Requires admin token in X-Admin-Token header.
    """
    logger.info(
        "admin.model.retrain",
        document_id=request.document_id,
        document_url=request.document_url,
        force_reindex=request.force_reindex,
    )

    # Check if document already exists
    existing = await session.execute(
        select(ComplianceDocument).where(ComplianceDocument.document_id == request.document_id)
    )
    existing_doc = existing.scalar_one_or_none()

    if existing_doc and not request.force_reindex:
        raise HTTPException(
            status_code=409,
            detail=f"Document {request.document_id} already exists. Use force_reindex=true to reindex.",
        )

    try:
        # Ingest document (downloads, extracts, chunks, embeds, stores in Redis)
        await ingest_document(
            source_url=request.document_url,
            document_id=request.document_id,
            document_title=request.document_title,
        )

        # Create or update document record
        if existing_doc:
            existing_doc.version += 1
            existing_doc.last_indexed_at = datetime.utcnow()
            existing_doc.updated_at = datetime.utcnow()
            doc = existing_doc
        else:
            doc = ComplianceDocument(
                document_id=request.document_id,
                title=request.document_title,
                document_type=request.document_type,
                source_url=request.document_url,
                version=1,
                is_active=True,
                last_indexed_at=datetime.utcnow(),
            )
            session.add(doc)

        await session.commit()
        await session.refresh(doc)

        # Create audit log
        audit_log = SystemAuditLog(
            event_type="model_retrained",
            actor_id=None,  # Admin action
            target_resource=f"document:{request.document_id}",
            action_details={
                "document_title": request.document_title,
                "document_url": request.document_url,
                "version": doc.version,
                "force_reindex": request.force_reindex,
            },
        )
        session.add(audit_log)
        await session.commit()

        logger.info(
            "admin.model.retrain.success",
            document_id=request.document_id,
            version=doc.version,
        )

        return {
            "status": "success",
            "document_id": str(doc.id),
            "document_title": doc.title,
            "version": doc.version,
            "message": "Document ingested and model updated successfully",
        }

    except Exception as e:
        logger.error(
            "admin.model.retrain.failed",
            error=str(e),
            document_id=request.document_id,
        )
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {str(e)}")


@router.delete("/users/{user_id}/queries")
async def gdpr_delete_user_data(
    user_id: str,
    confirm: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin),
):
    """
    GDPR data deletion - permanently delete all user queries and feedback.
    Requires confirmation token matching user_id.
    Requires admin token in X-Admin-Token header.
    """
    logger.warning("admin.gdpr.delete_requested", user_id=user_id)

    # Confirmation check
    if confirm != user_id:
        raise HTTPException(
            status_code=400,
            detail="Confirmation mismatch. Pass user_id as 'confirm' query parameter.",
        )

    # Get user
    user = await session.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Count data to be deleted
    queries_result = await session.execute(
        select(func.count(QueryLog.id)).where(QueryLog.user_id == user.id)
    )
    query_count = queries_result.scalar() or 0

    feedback_result = await session.execute(
        select(func.count(QueryFeedback.id)).where(QueryFeedback.user_id == user.id)
    )
    feedback_count = feedback_result.scalar() or 0

    # Delete feedback first (foreign key constraint)
    await session.execute(
        QueryFeedback.__table__.delete().where(QueryFeedback.user_id == user.id)
    )

    # Delete queries
    await session.execute(
        QueryLog.__table__.delete().where(QueryLog.user_id == user.id)
    )

    # Reset user statistics
    user.total_queries = 0
    user.queries_today = 0
    user.last_query_at = None

    await session.commit()

    # Create audit log
    audit_log = SystemAuditLog(
        event_type="gdpr_data_deletion",
        actor_id=None,  # Admin action
        target_resource=f"user:{user_id}",
        action_details={
            "queries_deleted": query_count,
            "feedback_deleted": feedback_count,
            "discord_id": user.discord_id,
        },
    )
    session.add(audit_log)
    await session.commit()

    logger.warning(
        "admin.gdpr.delete_completed",
        user_id=user_id,
        queries_deleted=query_count,
        feedback_deleted=feedback_count,
    )

    return {
        "status": "success",
        "user_id": str(user.id),
        "queries_deleted": query_count,
        "feedback_deleted": feedback_count,
        "message": "All user data permanently deleted (GDPR compliance)",
    }