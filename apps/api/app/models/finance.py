from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin


class Account(TimestampMixin, Base):
    __tablename__ = "account"
    __table_args__ = (
        Index("ix_account_user_plaid_account", "user_id", "plaid_account_id"),
        Index("ix_account_user_type", "user_id", "account_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), default="checking", nullable=False)
    institution: Mapped[str | None] = mapped_column(EncryptedText())
    current_balance: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    cash_projection_role: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plaid_account_id: Mapped[str | None] = mapped_column(String(140), index=True)
    plaid_item_id: Mapped[int | None] = mapped_column(Integer)
    mask: Mapped[str | None] = mapped_column(String(20))

    user: Mapped["User"] = relationship("User", back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="account")


class Category(TimestampMixin, Base):
    __tablename__ = "category"
    __table_args__ = (
        Index("ix_category_user_name", "user_id", "name"),
        Index("ix_category_user_budget_sort", "user_id", "budget_sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="expense", nullable=False)
    monthly_target: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    budget_group_key: Mapped[str | None] = mapped_column(String(80))
    budget_sort_order: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User | None"] = relationship("User", back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="category")
    transaction_splits: Mapped[list["TransactionSplit"]] = relationship("TransactionSplit", back_populates="category")
    rules: Mapped[list["CategoryRule"]] = relationship("CategoryRule", back_populates="category")


class CategoryRule(TimestampMixin, Base):
    __tablename__ = "category_rule"
    __table_args__ = (
        Index("ix_category_rule_user_category", "user_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), nullable=False)
    match_text: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="contains", nullable=False)
    rule_logic: Mapped[str] = mapped_column(String(20), default="all", nullable=False)
    conditions_json: Mapped[str | None] = mapped_column(EncryptedText())

    user: Mapped["User"] = relationship("User", back_populates="category_rules")
    category: Mapped[Category] = relationship("Category", back_populates="rules")


class Transaction(TimestampMixin, Base):
    __tablename__ = "transaction"
    __table_args__ = (
        Index("ix_transaction_user_posted_date", "user_id", "posted_date"),
        Index("ix_transaction_user_import_hash", "user_id", "import_hash"),
        Index("ix_transaction_user_plaid_transaction", "user_id", "plaid_transaction_id"),
        Index("ix_transaction_user_account", "user_id", "account_id"),
        Index("ix_transaction_user_category", "user_id", "category_id"),
        Index("ix_transaction_user_category_date", "user_id", "category_id", "posted_date"),
        Index("ix_transaction_user_account_date", "user_id", "account_id", "posted_date"),
        Index("ix_transaction_user_date_id", "user_id", "posted_date", "id"),
        Index("ix_transaction_user_amount_date", "user_id", "amount", "posted_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"))
    posted_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    merchant: Mapped[str | None] = mapped_column(EncryptedText())
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), default="expense", nullable=False)
    source_name: Mapped[str | None] = mapped_column(EncryptedText())
    import_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(EncryptedText())
    plaid_transaction_id: Mapped[str | None] = mapped_column(String(140), index=True)
    plaid_metadata: Mapped[str | None] = mapped_column(EncryptedText())
    pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="transactions")
    account: Mapped[Account | None] = relationship("Account", back_populates="transactions")
    category: Mapped[Category | None] = relationship("Category", back_populates="transactions")
    splits: Mapped[list["TransactionSplit"]] = relationship(
        "TransactionSplit",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="TransactionSplit.id",
    )

    @property
    def plaid_metadata_dict(self) -> dict:
        if not self.plaid_metadata:
            return {}
        try:
            loaded = json.loads(self.plaid_metadata)
        except (TypeError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _humanize_plaid_label(value: str | None) -> str:
        return (value or "").replace("_", " ").strip().title()

    @property
    def display_merchant(self) -> str:
        return self.merchant or self.description

    @property
    def raw_description(self) -> str | None:
        raw_value = self.plaid_metadata_dict.get("original_description")
        if raw_value and raw_value != self.display_merchant and raw_value != self.description:
            return raw_value
        if self.description and self.description != self.display_merchant:
            return self.description
        return None

    @property
    def plaid_category_label(self) -> str | None:
        category = self.plaid_metadata_dict.get("personal_finance_category") or {}
        if not isinstance(category, dict):
            return None
        return self._humanize_plaid_label(category.get("detailed") or category.get("primary"))

    @property
    def payment_channel_label(self) -> str | None:
        return self._humanize_plaid_label(self.plaid_metadata_dict.get("payment_channel"))

    @property
    def location_summary(self) -> str | None:
        location = self.plaid_metadata_dict.get("location") or {}
        if not isinstance(location, dict):
            return None
        city = location.get("city")
        region = location.get("region")
        store_number = location.get("store_number")
        parts = []
        if city and region:
            parts.append(f"{city}, {region}")
        elif city or region:
            parts.append(city or region)
        if store_number:
            parts.append(f"Store {store_number}")
        return " - ".join(parts) if parts else None


class TransactionSplit(TimestampMixin, Base):
    __tablename__ = "transaction_split"
    __table_args__ = (
        Index("ix_transaction_split_user_transaction", "user_id", "transaction_id"),
        Index("ix_transaction_split_user_category", "user_id", "category_id"),
        Index("ix_transaction_split_user_category_transaction", "user_id", "category_id", "transaction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transaction.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(EncryptedText())

    user: Mapped["User"] = relationship("User", back_populates="transaction_splits")
    transaction: Mapped[Transaction] = relationship("Transaction", back_populates="splits")
    category: Mapped[Category] = relationship("Category", back_populates="transaction_splits")
