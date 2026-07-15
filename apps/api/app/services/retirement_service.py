from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, User

RETIREMENT_ACCOUNT_TOKENS = ("401", "ira", "roth", "retirement", "pension", "fidelity", "vanguard")
RETIREMENT_WORKSHEET_FIELDS = (
    "retirement_lifestyle_notes",
    "retirement_location_notes",
    "retirement_healthcare_notes",
    "retirement_income_notes",
    "retirement_debt_notes",
    "retirement_family_notes",
)


def retirement_accounts_for_user(db: Session, user: User) -> list[Account]:
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    return [
        account
        for account in accounts
        if any(
            token in f"{account.name} {account.account_type} {account.institution}".lower()
            for token in RETIREMENT_ACCOUNT_TOKENS
        )
    ]
