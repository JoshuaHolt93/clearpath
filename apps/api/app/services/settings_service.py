from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AIUsageLog,
    CashProjectionRecurringIgnore,
    Category,
    CategoryRule,
    FixedExpenseItem,
    ForecastItem,
    Goal,
    HouseholdInvite,
    HouseholdMember,
    Insight,
    LoanPlan,
    MonthlyBudgetCategorySnapshot,
    MonthlyBudgetSnapshot,
    MonthlyPlan,
    PlaidAccountIgnore,
    PlaidItem,
    PlaidWebhookEvent,
    PrivilegedAccessLog,
    ProductFeedback,
    RecurringForecastTemplate,
    SecurityIncident,
    StripeWebhookEvent,
    Subscription,
    SubscriptionTransactionIgnore,
    Transaction,
    TransactionSplit,
    User,
    VariableExpenseItem,
)

# Faithful port of the Flask account-deletion surface (main.py at 92ccdbc).

ACCOUNT_DELETE_CONFIRMATION = "DELETE MY ACCOUNT"
ACCOUNT_DELETE_BLOCKING_BILLING_STATUSES = {
    "active",
    "trialing",
    "past_due",
    "unpaid",
    "incomplete",
    "incomplete_expired",
    "plan_selected",
    "checkout_complete",
}


def account_delete_requires_billing_cancellation(user: User) -> bool:
    if not getattr(user, "stripe_customer_id", None) and not getattr(user, "stripe_subscription_id", None):
        return False
    return (getattr(user, "billing_status", "") or "").strip().lower() in ACCOUNT_DELETE_BLOCKING_BILLING_STATUSES


def delete_user_account_data(db: Session, user: User) -> None:
    user_id = user.id
    stripe_customer_id = user.stripe_customer_id
    stripe_subscription_id = user.stripe_subscription_id
    plaid_item_ids = [row.id for row in db.scalars(select(PlaidItem).where(PlaidItem.user_id == user_id)).all()]

    if plaid_item_ids:
        db.query(PlaidWebhookEvent).filter(PlaidWebhookEvent.plaid_item_id.in_(plaid_item_ids)).delete(synchronize_session=False)

    db.query(TransactionSplit).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(SubscriptionTransactionIgnore).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Transaction).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(CategoryRule).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Goal).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(LoanPlan).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Subscription).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Account).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PlaidAccountIgnore).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(PlaidItem).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(ForecastItem).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(FixedExpenseItem).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(VariableExpenseItem).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(RecurringForecastTemplate).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(CashProjectionRecurringIgnore).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(MonthlyBudgetCategorySnapshot).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(MonthlyBudgetSnapshot).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(MonthlyPlan).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Insight).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(ProductFeedback).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(AIUsageLog).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(Category).filter_by(user_id=user_id).delete(synchronize_session=False)
    db.query(HouseholdInvite).filter(or_(HouseholdInvite.owner_user_id == user_id, HouseholdInvite.invited_by_user_id == user_id)).delete(synchronize_session=False)
    db.query(HouseholdMember).filter(or_(HouseholdMember.owner_user_id == user_id, HouseholdMember.invited_by_user_id == user_id)).delete(synchronize_session=False)

    stripe_filters = []
    if stripe_customer_id:
        stripe_filters.append(StripeWebhookEvent.raw_event_json.contains(stripe_customer_id))
    if stripe_subscription_id:
        stripe_filters.append(StripeWebhookEvent.raw_event_json.contains(stripe_subscription_id))
    if stripe_filters:
        db.query(StripeWebhookEvent).filter(or_(*stripe_filters)).delete(synchronize_session=False)

    db.query(PrivilegedAccessLog).filter_by(user_id=user_id).update({"user_id": None}, synchronize_session=False)
    db.query(SecurityIncident).filter_by(user_id=user_id).update({"user_id": None}, synchronize_session=False)
    db.delete(user)


# Flask parity note: the User ORM relationships carry delete-orphan cascades,
# but this function mirrors Flask's explicit bulk deletes so the removal order
# and the surviving (user_id-nulled) audit rows match production behavior.
