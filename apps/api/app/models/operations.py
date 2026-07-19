from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.auth import User

# Phase 6 operational models ported from Flask models.py at 92ccdbc:
# privileged-access auditing, security incidents (8c9f0bf), compliance
# control evaluations, Stripe webhook idempotency, and product feedback.


class PrivilegedAccessLog(TimestampMixin, Base):
    __tablename__ = "privileged_access_log"
    __table_args__ = (
        Index("ix_privileged_access_log_user_created", "user_id", "created_at"),
        Index("ix_privileged_access_log_success_created", "success", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    user: Mapped["User | None"] = relationship("User", back_populates="privileged_access_logs")


class ControlEvaluation(TimestampMixin, Base):
    __tablename__ = "control_evaluation"
    __table_args__ = (
        Index("ix_control_evaluation_control_evaluated", "control_id", "evaluated_at"),
        Index("ix_control_evaluation_status_evaluated", "status", "evaluated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    control_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    evidence: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)


class SecurityIncident(TimestampMixin, Base):
    __tablename__ = "security_incident"
    __table_args__ = (
        Index("ix_security_incident_status_deadline", "status", "report_deadline_at"),
        Index("ix_security_incident_type_detected", "incident_type", "detected_at"),
        Index("ix_security_incident_user_detected", "user_id", "detected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    report_deadline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), index=True)
    audit_notes: Mapped[str | None] = mapped_column(EncryptedText())

    user: Mapped["User | None"] = relationship("User")


class StripeWebhookEvent(TimestampMixin, Base):
    __tablename__ = "stripe_webhook_event"
    __table_args__ = (
        Index("ix_stripe_webhook_event_status_created", "status", "event_created"),
        Index("ix_stripe_webhook_event_type_created", "event_type", "event_created"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_created: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(30), default="processing", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw_event_json: Mapped[str | None] = mapped_column(Text)
    payload_hash: Mapped[str | None] = mapped_column(String(64), index=True)


class ProductFeedback(TimestampMixin, Base):
    __tablename__ = "product_feedback"
    __table_args__ = (
        Index("ix_product_feedback_user_type_created", "user_id", "feedback_type", "created_at"),
        Index("ix_product_feedback_reason_created", "reason", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    feedback_type: Mapped[str] = mapped_column(String(40), default="general", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), default="feedback", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    feature_expectation_reason: Mapped[str | None] = mapped_column(String(80))
    broken_features: Mapped[str | None] = mapped_column(EncryptedText())
    notify_when_addressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(EncryptedText())
    selected_plan: Mapped[str | None] = mapped_column(String(40))
    billing_status: Mapped[str | None] = mapped_column(String(40))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False, index=True)

    user: Mapped["User"] = relationship("User", back_populates="product_feedback")
