from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscription"
    __table_args__ = (
        Index("ix_subscription_user_merchant", "user_id", "merchant_key"),
        Index("ix_subscription_user_status", "user_id", "status"),
        Index("ix_subscription_user_next_charge", "user_id", "next_charge_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    merchant_key: Mapped[str] = mapped_column(String(140), nullable=False)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Consumer Subscriptions", nullable=False)
    service_category: Mapped[str] = mapped_column(String(80), default="Recurring", nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    monthly_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    annual_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    cycle: Mapped[str] = mapped_column(String(40), default="Monthly", nullable=False)
    cycle_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    cancel_url: Mapped[str | None] = mapped_column(EncryptedText())
    replaceable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen: Mapped[date | None] = mapped_column(Date)
    last_seen: Mapped[date | None] = mapped_column(Date)
    next_charge_date: Mapped[date | None] = mapped_column(Date)
    evidence: Mapped[str | None] = mapped_column(EncryptedText())
    notes: Mapped[str | None] = mapped_column(EncryptedText())
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cycle_is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")


class SubscriptionTransactionIgnore(TimestampMixin, Base):
    __tablename__ = "subscription_transaction_ignore"
    __table_args__ = (
        Index("ix_subscription_ignore_user_transaction", "user_id", "transaction_id"),
        Index("ix_subscription_ignore_user_merchant_amount", "user_id", "merchant_key", "amount"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transaction.id"), nullable=False, index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscription.id"))
    merchant_key: Mapped[str | None] = mapped_column(String(140))
    amount: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(EncryptedText())
