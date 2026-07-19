from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.crypto import EncryptedText
from app.core.defaults import SCHEMA_DEFAULT_PAYCHECK_CADENCE
from app.core.passwords import hash_password, verify_password
from app.core.security import generate_recovery_codes, generate_totp_secret, normalize_recovery_code
from app.models.base import Base, TimestampMixin, utc_now


class User(TimestampMixin, Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(EncryptedText())
    household_name: Mapped[str | None] = mapped_column(EncryptedText())
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ethics_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    ethics_policy_version: Mapped[str | None] = mapped_column(String(40))
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_recovery_codes: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    mfa_push_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_preferred_method: Mapped[str] = mapped_column(String(20), default="totp", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    billing_status: Mapped[str] = mapped_column(String(40), default="free", nullable=False, index=True)
    billing_price_id: Mapped[str | None] = mapped_column(String(120))
    selected_plan: Mapped[str] = mapped_column(String(40), default="basic", nullable=False, index=True)
    stripe_current_period_end: Mapped[datetime | None] = mapped_column(DateTime)
    ai_provider: Mapped[str] = mapped_column(String(40), default="openai", nullable=False)
    ai_model: Mapped[str] = mapped_column(String(120), default="gpt-5.5", nullable=False)
    ai_guidance_snapshot: Mapped[str | None] = mapped_column(EncryptedText())
    ai_guidance_generated_at: Mapped[datetime | None] = mapped_column(DateTime)
    cash_projection_calendar_token: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    cash_projection_calendar_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    cash_projection_calendar_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cash_projection_calendar_generated_at: Mapped[datetime | None] = mapped_column(DateTime)
    cash_projection_default_horizon: Mapped[str] = mapped_column(String(20), default="1m", nullable=False)

    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories: Mapped[list["Category"]] = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    category_rules: Mapped[list["CategoryRule"]] = relationship("CategoryRule", back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    transaction_splits: Mapped[list["TransactionSplit"]] = relationship("TransactionSplit", back_populates="user", cascade="all, delete-orphan")
    plaid_items: Mapped[list["PlaidItem"]] = relationship("PlaidItem", back_populates="user", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    monthly_plans: Mapped[list["MonthlyPlan"]] = relationship("MonthlyPlan", back_populates="user", cascade="all, delete-orphan")
    monthly_budget_snapshots: Mapped[list["MonthlyBudgetSnapshot"]] = relationship("MonthlyBudgetSnapshot", back_populates="user", cascade="all, delete-orphan")
    monthly_budget_category_snapshots: Mapped[list["MonthlyBudgetCategorySnapshot"]] = relationship(
        "MonthlyBudgetCategorySnapshot", back_populates="user", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship("Insight", back_populates="user", cascade="all, delete-orphan")
    forecast_items: Mapped[list["ForecastItem"]] = relationship("ForecastItem", back_populates="user", cascade="all, delete-orphan")
    ai_usage_logs: Mapped[list["AIUsageLog"]] = relationship("AIUsageLog", back_populates="user", cascade="all, delete-orphan")
    # Flask parity: privileged-access logs survive account deletion (user_id is
    # nulled, not cascaded); product feedback rows are deleted explicitly by
    # delete_user_account_data. Neither uses delete-orphan.
    privileged_access_logs: Mapped[list["PrivilegedAccessLog"]] = relationship("PrivilegedAccessLog", back_populates="user")
    product_feedback: Mapped[list["ProductFeedback"]] = relationship("ProductFeedback", back_populates="user")
    profile: Mapped[OnboardingProfile | None] = relationship(back_populates="user", cascade="all, delete-orphan")
    household_members: Mapped[list[HouseholdMember]] = relationship(
        back_populates="owner_user",
        foreign_keys="HouseholdMember.owner_user_id",
        cascade="all, delete-orphan",
    )
    household_invites: Mapped[list[HouseholdInvite]] = relationship(
        back_populates="owner_user",
        foreign_keys="HouseholdInvite.owner_user_id",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(self.password_hash, password)

    def ensure_mfa_secret(self) -> str:
        if not self.mfa_secret:
            self.mfa_secret = generate_totp_secret()
        return self.mfa_secret

    def generate_mfa_recovery_codes(self, count: int = 10) -> list[str]:
        codes = generate_recovery_codes(count)
        self.set_mfa_recovery_codes(codes)
        return codes

    def set_mfa_recovery_codes(self, codes: list[str]) -> None:
        self.mfa_recovery_codes = json.dumps([hash_password(normalize_recovery_code(code)) for code in codes])

    def mfa_recovery_code_hashes(self) -> list[str]:
        if not self.mfa_recovery_codes:
            return []
        try:
            loaded = json.loads(self.mfa_recovery_codes)
        except (TypeError, ValueError):
            return []
        return loaded if isinstance(loaded, list) else []

    def verify_mfa_recovery_code(self, code: str | None) -> bool:
        normalized = normalize_recovery_code(code)
        if not normalized:
            return False
        hashes = self.mfa_recovery_code_hashes()
        for index, recovery_hash in enumerate(hashes):
            if verify_password(recovery_hash, normalized):
                del hashes[index]
                self.mfa_recovery_codes = json.dumps(hashes)
                return True
        return False


class HouseholdMember(TimestampMixin, Base):
    __tablename__ = "household_member"
    __table_args__ = (
        Index("ix_household_member_owner_status", "owner_user_id", "status"),
        Index("ix_household_member_owner_role", "owner_user_id", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(EncryptedText())
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_recovery_codes: Mapped[str | None] = mapped_column(EncryptedText(redact_card_data=False))
    mfa_push_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_preferred_method: Mapped[str] = mapped_column(String(20), default="totp", nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    policy_version: Mapped[str | None] = mapped_column(String(40))

    owner_user: Mapped[User] = relationship(foreign_keys=[owner_user_id], back_populates="household_members")
    invited_by_user: Mapped[User] = relationship(foreign_keys=[invited_by_user_id])

    def set_password(self, password: str) -> None:
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        return verify_password(self.password_hash, password)

    def ensure_mfa_secret(self) -> str:
        if not self.mfa_secret:
            self.mfa_secret = generate_totp_secret()
        return self.mfa_secret

    def generate_mfa_recovery_codes(self, count: int = 10) -> list[str]:
        codes = generate_recovery_codes(count)
        self.set_mfa_recovery_codes(codes)
        return codes

    def set_mfa_recovery_codes(self, codes: list[str]) -> None:
        self.mfa_recovery_codes = json.dumps([hash_password(normalize_recovery_code(code)) for code in codes])

    def mfa_recovery_code_hashes(self) -> list[str]:
        if not self.mfa_recovery_codes:
            return []
        try:
            loaded = json.loads(self.mfa_recovery_codes)
        except (TypeError, ValueError):
            return []
        return loaded if isinstance(loaded, list) else []

    def verify_mfa_recovery_code(self, code: str | None) -> bool:
        normalized = normalize_recovery_code(code)
        if not normalized:
            return False
        hashes = self.mfa_recovery_code_hashes()
        for index, recovery_hash in enumerate(hashes):
            if verify_password(recovery_hash, normalized):
                del hashes[index]
                self.mfa_recovery_codes = json.dumps(hashes)
                return True
        return False


class HouseholdInvite(TimestampMixin, Base):
    __tablename__ = "household_invite"
    __table_args__ = (
        Index("ix_household_invite_owner_status", "owner_user_id", "status"),
        Index("ix_household_invite_email_status", "email", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    invited_by_user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    accepted_member_id: Mapped[int | None] = mapped_column(ForeignKey("household_member.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    owner_user: Mapped[User] = relationship(foreign_keys=[owner_user_id], back_populates="household_invites")
    invited_by_user: Mapped[User] = relationship(foreign_keys=[invited_by_user_id])
    accepted_member: Mapped[HouseholdMember | None] = relationship(foreign_keys=[accepted_member_id])


class LoginAttempt(TimestampMixin, Base):
    __tablename__ = "login_attempt"
    __table_args__ = (Index("ix_login_attempt_key_attempted_at", "key", "attempted_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class OnboardingProfile(TimestampMixin, Base):
    __tablename__ = "onboarding_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, unique=True)
    income_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    income_basis: Mapped[str] = mapped_column(String(20), default="take_home", nullable=False)
    income_type: Mapped[str] = mapped_column(String(20), default="salary", nullable=False)
    income_frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    paycheck_cadence: Mapped[str] = mapped_column(String(20), default=SCHEMA_DEFAULT_PAYCHECK_CADENCE, nullable=False)
    next_pay_date: Mapped[date | None] = mapped_column(Date)
    paycheck_second_date: Mapped[date | None] = mapped_column(Date)
    paycheck_days_of_week: Mapped[str | None] = mapped_column(String(30))
    paycheck_second_day_of_month: Mapped[int | None] = mapped_column(Integer)
    paycheck_monthly_week_numbers: Mapped[str | None] = mapped_column(String(20))
    paycheck_monthly_weekday: Mapped[int | None] = mapped_column(Integer)
    hourly_hours_per_week: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    monthly_income: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    fixed_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    variable_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    additional_income_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    additional_income_frequency: Mapped[str] = mapped_column(String(20), default="annual", nullable=False)
    planned_savings_contribution: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_debt_payment: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    target_investment_contribution: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    tax_state: Mapped[str | None] = mapped_column(String(2))
    tax_filing_status: Mapped[str] = mapped_column(String(30), default="married_joint", nullable=False)
    tax_gross_annual_income: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    tax_state_effective_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    tax_additional_label: Mapped[str] = mapped_column(String(80), default="Additional Local Tax", nullable=False)
    tax_additional_type: Mapped[str] = mapped_column(String(20), default="amount", nullable=False)
    tax_additional_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    tax_additional_monthly_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    include_payroll_taxes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retirement_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retirement_has_employer_plan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retirement_employer_withheld: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retirement_has_personal_plan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retirement_monthly_contribution: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    retirement_personal_monthly_contribution: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    retirement_lifestyle_notes: Mapped[str | None] = mapped_column(EncryptedText())
    retirement_location_notes: Mapped[str | None] = mapped_column(EncryptedText())
    retirement_healthcare_notes: Mapped[str | None] = mapped_column(EncryptedText())
    retirement_income_notes: Mapped[str | None] = mapped_column(EncryptedText())
    retirement_debt_notes: Mapped[str | None] = mapped_column(EncryptedText())
    retirement_family_notes: Mapped[str | None] = mapped_column(EncryptedText())
    notes: Mapped[str | None] = mapped_column(EncryptedText())

    user: Mapped[User] = relationship(back_populates="profile")
