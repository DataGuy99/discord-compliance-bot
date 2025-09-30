"""
Database models for S&P Compliance Discord Bot
5 models with full audit trail and RBAC support
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Index,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class User(Base):
    """
    Discord user with RBAC and permissions tracking
    25 fields as per spec
    """
    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Discord Identity
    discord_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    discord_username: Mapped[str] = mapped_column(String(100), nullable=False)
    discord_discriminator: Mapped[str] = mapped_column(String(10), nullable=False)
    discord_avatar: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # RBAC
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")  # user, admin, compliance_officer
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Usage Statistics
    total_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queries_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_query_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Rate Limiting
    rate_limit_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    daily_query_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Guild Association
    guild_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    guild_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Preferences
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    notification_preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    queries: Mapped[list["QueryLog"]] = relationship("QueryLog", back_populates="user", cascade="all, delete-orphan")
    feedbacks: Mapped[list["QueryFeedback"]] = relationship("QueryFeedback", back_populates="user", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_user_discord_id", "discord_id"),
        Index("idx_user_guild_id", "guild_id"),
        Index("idx_user_role", "role"),
    )


class QueryLog(Base):
    """
    Complete query and response audit log
    20 fields as per spec
    """
    __tablename__ = "query_logs"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User Reference
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Query Content
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # For deduplication

    # Response
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high

    # Model Performance
    model_used: Mapped[str] = mapped_column(String(50), nullable=False, default="grok-4-latest")
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # RAG Context
    rag_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rag_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # List of source documents

    # Session Tracking
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    context_messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Flagging
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flag_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="queries")
    feedback: Mapped[Optional["QueryFeedback"]] = relationship("QueryFeedback", back_populates="query", uselist=False)

    # Indexes
    __table_args__ = (
        Index("idx_query_user_id", "user_id"),
        Index("idx_query_hash", "query_hash"),
        Index("idx_query_created_at", "created_at"),
        Index("idx_query_session_id", "session_id"),
        Index("idx_query_flagged", "is_flagged"),
    )


class QueryFeedback(Base):
    """
    User feedback on query responses
    12 fields as per spec
    """
    __tablename__ = "query_feedbacks"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Ratings (1-5 scale)
    overall_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    helpfulness_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy_rating: Mapped[int] = mapped_column(Integer, nullable=False)

    # Feedback Text
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Follow-up Actions
    follow_up_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    follow_up_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="feedbacks")
    query: Mapped["QueryLog"] = relationship("QueryLog", back_populates="feedback")

    # Indexes
    __table_args__ = (
        Index("idx_feedback_user_id", "user_id"),
        Index("idx_feedback_query_id", "query_id"),
    )


class ComplianceDocument(Base):
    """
    S&P policy and procedure document storage
    18 fields as per spec
    """
    __tablename__ = "compliance_documents"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document Identity
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    document_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)  # policy, procedure, regulation
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Access Control
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    access_level: Mapped[str] = mapped_column(String(50), nullable=False, default="public")

    # Lifecycle
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiration_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Source
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 of content

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_document_id", "document_id"),
        Index("idx_document_type", "document_type"),
        Index("idx_document_category", "category"),
        Index("idx_document_active", "is_active"),
    )


class SystemAuditLog(Base):
    """
    Administrative action and system event logging
    15 fields as per spec
    """
    __tablename__ = "system_audit_logs"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Event Type
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # user_created, query_flagged, etc.
    event_category: Mapped[str] = mapped_column(String(50), nullable=False)  # auth, query, admin, system
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")  # debug, info, warning, error, critical

    # Actor
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # User who performed action
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False, default="user")  # user, system, api

    # Target
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # user, query, document
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Details
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Request Context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # GDPR Compliance
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    # Indexes
    __table_args__ = (
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_category", "event_category"),
        Index("idx_audit_severity", "severity"),
        Index("idx_audit_actor_id", "actor_id"),
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_request_id", "request_id"),
    )