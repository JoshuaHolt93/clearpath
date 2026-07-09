from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin


class PlaidItem(TimestampMixin, Base):
    __tablename__ = "plaid_item"
    __table_args__ = (
        Index("ix_plaid_item_user_item", "user_id", "plaid_item_id"),
        Index("ix_plaid_item_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    plaid_item_id: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    # Encrypted Fernet token only. Raw Plaid access tokens must never be assigned or exposed here.
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    institution_name: Mapped[str | None] = mapped_column(EncryptedText())
    institution_id: Mapped[str | None] = mapped_column(String(80))
    sync_cursor: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    status: Mapped[str] = mapped_column(String(40), default="connected", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(EncryptedText())
    consent_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    reconnect_required_at: Mapped[datetime | None] = mapped_column(DateTime)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship("User", back_populates="plaid_items")


class PlaidAccountIgnore(TimestampMixin, Base):
    __tablename__ = "plaid_account_ignore"
    __table_args__ = (
        Index("ix_plaid_account_ignore_user_account", "user_id", "plaid_account_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    plaid_item_id: Mapped[int | None] = mapped_column(ForeignKey("plaid_item.id"))
    plaid_account_id: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    account_name: Mapped[str | None] = mapped_column(EncryptedText())
    institution_name: Mapped[str | None] = mapped_column(EncryptedText())


class PlaidWebhookEvent(TimestampMixin, Base):
    __tablename__ = "plaid_webhook_event"
    __table_args__ = (
        Index("ix_plaid_webhook_event_status_created", "status", "created_at"),
        Index("ix_plaid_webhook_event_type_code", "webhook_type", "webhook_code"),
        Index("ix_plaid_webhook_event_item_created", "plaid_item_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    plaid_item_id: Mapped[int | None] = mapped_column(ForeignKey("plaid_item.id"))
    webhook_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    webhook_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="processing", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
