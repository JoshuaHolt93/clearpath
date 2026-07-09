from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.plaid_policy import assert_plaid_data_purpose
from app.models import Subscription, SubscriptionTransactionIgnore, Transaction, User
from app.services import plaid_service
from app.services.transaction_service import parse_amount

# Faithful port of Flask subscription_service.py plus the evidence helpers
# from main.py. The Flask request-scoped cache around subscription_summary is
# an optimization dropped here (each API call computes directly); the
# timed_function observability decorator is likewise deferred.

SUBSCRIPTION_CATEGORY = "Consumer Subscriptions"
SUBSCRIPTION_STATUSES = {
    "active": "Active",
    "review": "Needs Review",
    "canceling": "Canceling",
    "canceled": "Canceled",
    "ignored": "Ignored",
}

KNOWN_SERVICES = {
    "netflix": {"name": "Netflix", "category": "Streaming", "cancel_url": "https://www.netflix.com/cancelplan", "replaceable": True},
    "spotify": {"name": "Spotify", "category": "Music", "cancel_url": "https://www.spotify.com/account/subscription/", "replaceable": False},
    "adobe": {"name": "Adobe Creative Cloud", "category": "Software", "cancel_url": "https://account.adobe.com/plans", "replaceable": True},
    "openai": {"name": "ChatGPT", "category": "AI Tools", "cancel_url": "https://platform.openai.com/account/billing/overview", "replaceable": False},
    "anthropic": {"name": "Claude", "category": "AI Tools", "cancel_url": "https://claude.ai/settings/billing", "replaceable": False},
    "perplexity": {"name": "Perplexity", "category": "AI Tools", "cancel_url": "https://www.perplexity.ai/settings", "replaceable": True},
    "midjourney": {"name": "Midjourney", "category": "AI Tools", "cancel_url": "https://www.midjourney.com/account/", "replaceable": True},
    "cursor": {"name": "Cursor", "category": "AI Tools", "cancel_url": "https://cursor.com/settings", "replaceable": True},
    "elevenlabs": {"name": "ElevenLabs", "category": "AI Tools", "cancel_url": "https://elevenlabs.io/app/subscription", "replaceable": True},
    "dropbox": {"name": "Dropbox", "category": "Cloud Storage", "cancel_url": "https://www.dropbox.com/account/plan", "replaceable": True},
    "nytimes": {"name": "The New York Times", "category": "News", "cancel_url": "https://myaccount.nytimes.com/seg/subscription", "replaceable": True},
    "washingtonpost": {"name": "The Washington Post", "category": "News", "cancel_url": "https://subscribe.washingtonpost.com/profile/#/profile/access", "replaceable": True},
    "wsj": {"name": "The Wall Street Journal", "category": "News", "cancel_url": "https://customercenter.wsj.com/", "replaceable": True},
    "substack": {"name": "Substack", "category": "News", "cancel_url": "https://substack.com/settings", "replaceable": True},
    "classpass": {"name": "ClassPass", "category": "Fitness", "cancel_url": "https://classpass.com/settings/account", "replaceable": True},
    "planetfitness": {"name": "Planet Fitness", "category": "Fitness", "cancel_url": "https://www.planetfitness.com/about-planet-fitness/customer-service", "replaceable": True},
    "amazon": {"name": "Amazon Prime", "category": "Shopping", "cancel_url": "https://www.amazon.com/amazonprime", "replaceable": False},
    "figma": {"name": "Figma", "category": "Design", "cancel_url": "https://www.figma.com/files/team", "replaceable": False},
    "hulu": {"name": "Hulu", "category": "Streaming", "cancel_url": "https://secure.hulu.com/account", "replaceable": True},
    "disney": {"name": "Disney+", "category": "Streaming", "cancel_url": "https://www.disneyplus.com/account", "replaceable": True},
    "youtube": {"name": "YouTube Premium", "category": "Streaming", "cancel_url": "https://www.youtube.com/paid_memberships", "replaceable": True},
    "max": {"name": "Max", "category": "Streaming", "cancel_url": "https://www.max.com/subscription", "replaceable": True},
    "paramount": {"name": "Paramount+", "category": "Streaming", "cancel_url": "https://www.paramountplus.com/account/", "replaceable": True},
    "peacock": {"name": "Peacock", "category": "Streaming", "cancel_url": "https://www.peacocktv.com/account", "replaceable": True},
    "espn": {"name": "ESPN+", "category": "Streaming", "cancel_url": "https://plus.espn.com/account", "replaceable": True},
    "sling": {"name": "Sling TV", "category": "Streaming", "cancel_url": "https://www.sling.com/account", "replaceable": True},
    "audible": {"name": "Audible", "category": "Books", "cancel_url": "https://www.audible.com/account/membership", "replaceable": True},
    "apple": {"name": "Apple", "category": "Digital", "cancel_url": "https://support.apple.com/billing", "replaceable": False},
    "microsoft": {"name": "Microsoft 365", "category": "Software", "cancel_url": "https://account.microsoft.com/services", "replaceable": True},
    "google": {"name": "Google One", "category": "Cloud Storage", "cancel_url": "https://one.google.com/settings", "replaceable": True},
    "canva": {"name": "Canva", "category": "Design", "cancel_url": "https://www.canva.com/settings/billing-and-plans", "replaceable": True},
    "notion": {"name": "Notion", "category": "Productivity", "cancel_url": "https://www.notion.so/my-account", "replaceable": False},
    "zoom": {"name": "Zoom", "category": "Productivity", "cancel_url": "https://zoom.us/billing", "replaceable": True},
    "github": {"name": "GitHub", "category": "Developer Tools", "cancel_url": "https://github.com/settings/billing", "replaceable": False},
    "patreon": {"name": "Patreon", "category": "Creator Support", "cancel_url": "https://www.patreon.com/settings/memberships", "replaceable": True},
    "grammarly": {"name": "Grammarly", "category": "Productivity", "cancel_url": "https://account.grammarly.com/subscription", "replaceable": True},
    "duolingo": {"name": "Duolingo", "category": "Education", "cancel_url": "https://www.duolingo.com/settings/super", "replaceable": True},
    "linkedin": {"name": "LinkedIn Premium", "category": "Career", "cancel_url": "https://www.linkedin.com/premium/manage/", "replaceable": True},
}

ALIASES = {
    "netflix": ["netflix"],
    "spotify": ["spotify"],
    "adobe": ["adobe"],
    "openai": ["openai", "chatgpt"],
    "anthropic": ["anthropic", "claude"],
    "perplexity": ["perplexity"],
    "midjourney": ["midjourney"],
    "cursor": ["cursor"],
    "elevenlabs": ["elevenlabs", "eleven labs"],
    "dropbox": ["dropbox"],
    "nytimes": ["nytimes", "new york times"],
    "washingtonpost": ["washington post", "washpost"],
    "wsj": ["wall street journal", "wsj"],
    "substack": ["substack"],
    "classpass": ["classpass"],
    "planetfitness": ["planet fitness"],
    "amazon": ["amazon prime", "amzn prime"],
    "figma": ["figma"],
    "hulu": ["hulu"],
    "disney": ["disney", "disney plus", "disney+"],
    "youtube": ["youtube premium", "google youtube", "youtube"],
    "max": ["hbo max", "hbomax", "max.com", "max subscription"],
    "paramount": ["paramount plus", "paramount+"],
    "peacock": ["peacock"],
    "espn": ["espn plus", "espn+"],
    "sling": ["sling"],
    "audible": ["audible"],
    "apple": ["apple.com/bill", "itunes", "icloud", "apple tv"],
    "microsoft": ["microsoft", "office 365", "microsoft 365"],
    "google": ["google one", "google storage"],
    "canva": ["canva"],
    "notion": ["notion"],
    "zoom": ["zoom"],
    "github": ["github"],
    "patreon": ["patreon"],
    "grammarly": ["grammarly"],
    "duolingo": ["duolingo"],
    "linkedin": ["linkedin premium"],
}

STOP_WORDS = {
    "pos", "debit", "card", "purchase", "recurring", "payment", "online", "bill", "visa", "mc",
    "web", "inc", "llc", "co", "com", "hd", "usa", "autopay", "auto", "sq", "tst",
}

CYCLES = [
    {"cycle": "Weekly", "days": 7, "monthly_multiplier": 52 / 12},
    {"cycle": "Biweekly", "days": 14, "monthly_multiplier": 26 / 12},
    {"cycle": "Monthly", "days": 30, "monthly_multiplier": 1},
    {"cycle": "Quarterly", "days": 91, "monthly_multiplier": 1 / 3},
    {"cycle": "Annual", "days": 365, "monthly_multiplier": 1 / 12},
]
SUBSCRIPTION_CYCLE_OPTIONS = {cycle["cycle"]: cycle for cycle in CYCLES}

SUBSCRIPTION_KEYWORDS = {
    "subscription",
    "membership",
    "monthly",
    "annual",
    "annually",
    "premium",
    "plus",
    "pro",
    "renewal",
    "recurring",
}

COMMON_PURCHASE_CATEGORY_NAMES = {
    "dining",
    "gas",
    "groceries",
    "shopping",
}

COMMON_PURCHASE_MERCHANT_TERMS = {
    "7 eleven",
    "circle k",
    "costco",
    "cvs",
    "exxon",
    "kroger",
    "mcdonald",
    "mcdonalds",
    "quiktrip",
    "shell",
    "speedway",
    "starbucks",
    "target",
    "walmart",
    "walgreens",
}


def normalize_subscription_merchant(description: str) -> str:
    cleaned = re.sub(r"https?://|www\.", " ", (description or "").lower())
    cleaned = re.sub(r"[*#:/\\|_-]+", " ", cleaned)
    cleaned = re.sub(r"\b\d{3,}\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s&+]", " ", cleaned)
    tokens = [token for token in cleaned.split() if token and token not in STOP_WORDS]
    normalized = " ".join(tokens)
    for key, names in ALIASES.items():
        if any(alias in normalized for alias in names):
            return key
    return " ".join(tokens[:2]) or "unknown"


def title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in value.replace("-", " ").split())


def days_between(first: date, second: date) -> int:
    return abs((second - first).days)


def best_cycle(intervals: list[int]) -> dict | None:
    if not intervals:
        return None
    median = sorted(intervals)[len(intervals) // 2]
    scored = []
    for cycle in CYCLES:
        fit = max(0, 1 - abs(median - cycle["days"]) / max(7, cycle["days"] * 0.12))
        scored.append({**cycle, "fit": fit})
    best = sorted(scored, key=lambda row: row["fit"], reverse=True)[0]
    return best if best["fit"] > 0.35 else None


def default_monthly_cycle() -> dict:
    return {"cycle": "Monthly", "days": 30, "monthly_multiplier": 1, "fit": 0.8}


def has_subscription_signal(transactions: list[Transaction]) -> bool:
    text = " ".join(
        f"{txn.description or ''} {txn.merchant or ''}"
        for txn in transactions
    ).lower()
    return any(keyword in text for keyword in SUBSCRIPTION_KEYWORDS)


def looks_like_common_purchase_behavior(merchant_key: str, transactions: list[Transaction]) -> bool:
    merchant_text = f"{merchant_key} " + " ".join(f"{txn.description or ''} {txn.merchant or ''}" for txn in transactions)
    normalized_text = normalize_subscription_merchant(merchant_text)
    raw_text = merchant_text.lower()
    if any(term in normalized_text or term in raw_text for term in COMMON_PURCHASE_MERCHANT_TERMS):
        return True

    category_names = {
        (txn.category.name or "").strip().lower()
        for txn in transactions
        if txn.category and txn.category.name
    }
    return bool(category_names & COMMON_PURCHASE_CATEGORY_NAMES)


def candidate_from_group(merchant_key: str, group: list[Transaction], cycle: dict, confidence: float, *, catalog_match: bool) -> dict:
    sorted_group = sorted(group, key=lambda txn: (txn.posted_date, txn.id))
    amounts = [abs(txn.amount) for txn in sorted_group]
    average_amount = sum(amounts) / len(amounts)
    service = KNOWN_SERVICES.get(merchant_key, {})
    monthly_amount = round(average_amount * cycle["monthly_multiplier"], 2)
    last_seen = sorted_group[-1].posted_date
    return {
        "merchant_key": merchant_key,
        "name": service.get("name") or title_case(merchant_key),
        "category": SUBSCRIPTION_CATEGORY,
        "service_category": service.get("category") or "Recurring",
        "amount": round(average_amount, 2),
        "monthly_amount": monthly_amount,
        "annual_amount": round(monthly_amount * 12, 2),
        "cycle": cycle["cycle"],
        "cycle_days": cycle["days"],
        "confidence": round(confidence, 4),
        "status": "active" if catalog_match or confidence >= 0.65 else "review",
        "cancel_url": service.get("cancel_url"),
        "replaceable": service.get("replaceable", True),
        "first_seen": sorted_group[0].posted_date,
        "last_seen": last_seen,
        "next_charge_date": last_seen + timedelta(days=cycle["days"]),
        "evidence": json.dumps(
            [
                {
                    "id": txn.id,
                    "date": txn.posted_date.isoformat(),
                    "description": txn.description,
                    "amount": abs(txn.amount),
                }
                for txn in sorted_group[-6:]
            ]
        ),
    }


def amount_is_consistent(transactions: list[Transaction], tolerance: float = 0.03) -> bool:
    if len(transactions) <= 1:
        return True
    amounts = [abs(txn.amount) for txn in transactions]
    average_amount = sum(amounts) / len(amounts)
    if average_amount <= 0:
        return False
    average_variance = sum(abs(amount - average_amount) for amount in amounts) / len(amounts)
    return average_variance <= max(0.75, average_amount * tolerance)


def best_amount_cluster(transactions: list[Transaction]) -> list[Transaction]:
    clusters: dict[float, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        clusters[round(abs(transaction.amount), 2)].append(transaction)
    return sorted(
        clusters.values(),
        key=lambda group: (len(group), max(txn.posted_date for txn in group), sum(abs(txn.amount) for txn in group)),
        reverse=True,
    )[0]


def detect_subscription_candidates(db: Session, user: User, *, purpose: str = "subscriptions") -> list[dict]:
    assert_plaid_data_purpose(purpose)
    ignored_rows = db.scalars(select(SubscriptionTransactionIgnore).where(SubscriptionTransactionIgnore.user_id == user.id)).all()
    ignored_transaction_ids = {row.transaction_id for row in ignored_rows}
    ignored_vendor_amounts = {
        (row.merchant_key, round(abs(row.amount), 2))
        for row in ignored_rows
        if row.merchant_key and row.amount is not None
    }
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user.id, Transaction.amount < 0)
        .order_by(Transaction.posted_date.asc(), Transaction.id.asc())
    ).all()
    merchant_groups: dict[str, list[Transaction]] = defaultdict(list)
    amount_groups: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        if transaction.id in ignored_transaction_ids:
            continue
        merchant = normalize_subscription_merchant(transaction.description)
        if (merchant, round(abs(transaction.amount), 2)) in ignored_vendor_amounts:
            continue
        merchant_groups[merchant].append(transaction)
        amount_bucket = round(abs(transaction.amount) / 2)
        amount_groups[f"{merchant}|{amount_bucket}"].append(transaction)

    detected = []
    detected_merchants = set()

    for merchant_key, group in merchant_groups.items():
        if merchant_key not in KNOWN_SERVICES:
            continue
        original_group = group
        group = best_amount_cluster(group)
        if len(original_group) > 1 and len(group) == 1 and not has_subscription_signal(group):
            continue
        if len(group) > 1 and not amount_is_consistent(group):
            continue
        intervals = [days_between(group[index - 1].posted_date, txn.posted_date) for index, txn in enumerate(group[1:], start=1)]
        cycle = best_cycle(intervals) if intervals else default_monthly_cycle()
        detected.append(candidate_from_group(merchant_key, group, cycle or default_monthly_cycle(), 0.9 if len(group) == 1 else 0.95, catalog_match=True))
        detected_merchants.add(merchant_key)

    for merchant_key, group in merchant_groups.items():
        if merchant_key in detected_merchants:
            continue
        subscription_marked = [
            txn
            for txn in group
            if txn.category and (txn.category.name or "").strip().lower() == SUBSCRIPTION_CATEGORY.lower()
        ]
        if not subscription_marked:
            continue
        group = best_amount_cluster(subscription_marked)
        intervals = [days_between(group[index - 1].posted_date, txn.posted_date) for index, txn in enumerate(group[1:], start=1)]
        cycle = best_cycle(intervals) if intervals else default_monthly_cycle()
        detected.append(candidate_from_group(merchant_key, group, cycle or default_monthly_cycle(), 0.82, catalog_match=True))
        detected_merchants.add(merchant_key)

    for group in amount_groups.values():
        if len(group) < 2:
            continue
        merchant_key = normalize_subscription_merchant(group[0].description)
        if (
            merchant_key in detected_merchants
            or looks_like_common_purchase_behavior(merchant_key, group)
            or not has_subscription_signal(group)
        ):
            continue
        intervals = [days_between(group[index - 1].posted_date, txn.posted_date) for index, txn in enumerate(group[1:], start=1)]
        cycle = best_cycle(intervals)
        if not cycle:
            continue
        amounts = [abs(txn.amount) for txn in group]
        average_amount = sum(amounts) / len(amounts)
        amount_variance = sum(abs(amount - average_amount) for amount in amounts) / len(amounts)
        if amount_variance > max(0.75, average_amount * 0.03):
            continue
        amount_fit = max(0, 1 - amount_variance / max(2, average_amount * 0.1))
        count_bonus = min(1, (len(group) - 2) / 3)
        confidence = max(0, min(1, cycle["fit"] * 0.5 + amount_fit * 0.3 + count_bonus * 0.2))
        if confidence < 0.45:
            continue
        detected.append(candidate_from_group(merchant_key, group, cycle, confidence, catalog_match=False))
    return sorted(detected, key=lambda row: row["monthly_amount"], reverse=True)


def scan_and_sync_subscriptions(db: Session, user: User, *, purpose: str = "subscriptions") -> list[Subscription]:
    assert_plaid_data_purpose(purpose)
    candidates = detect_subscription_candidates(db, user, purpose=purpose)
    existing = {
        subscription.merchant_key: subscription
        for subscription in db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    }
    synced = []
    for candidate in candidates:
        subscription = existing.get(candidate["merchant_key"])
        if subscription and subscription.status == "ignored":
            continue
        if not subscription:
            subscription = Subscription(user_id=user.id, merchant_key=candidate["merchant_key"])
        preserved_status = subscription.status if subscription.id and subscription.status in {"canceling", "canceled", "ignored"} else candidate["status"]
        manual_cycle = bool(subscription.cycle_is_manual)
        preserved_cycle = subscription.cycle
        preserved_cycle_days = subscription.cycle_days
        for key, value in candidate.items():
            setattr(subscription, key, value)
        if manual_cycle:
            cycle = SUBSCRIPTION_CYCLE_OPTIONS.get(preserved_cycle, SUBSCRIPTION_CYCLE_OPTIONS["Monthly"])
            subscription.cycle = preserved_cycle
            subscription.cycle_days = preserved_cycle_days or cycle["days"]
            subscription.monthly_amount = round(subscription.amount * cycle["monthly_multiplier"], 2)
            subscription.annual_amount = round(subscription.monthly_amount * 12, 2)
            subscription.cycle_is_manual = True
        subscription.status = preserved_status
        subscription.is_manual = False
        db.add(subscription)
        synced.append(subscription)
    db.commit()
    return synced


def active_subscription_rows(db: Session, user: User, *, purpose: str = "subscriptions") -> list[dict]:
    assert_plaid_data_purpose(purpose)
    subscriptions = sorted(
        db.scalars(
            select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "review", "canceling"]))
        ).all(),
        key=lambda subscription: (-subscription.monthly_amount, (subscription.name or "").lower()),
    )
    return [
        {
            "subscription": subscription,
            "label": subscription.name,
            "amount": subscription.monthly_amount,
        }
        for subscription in subscriptions
    ]


def subscription_category_breakdown(subscriptions: list[Subscription]) -> list[dict]:
    active = [sub for sub in subscriptions if sub.status not in {"canceled", "ignored"}]
    total = sum(sub.monthly_amount for sub in active)
    categories: dict[str, float] = defaultdict(float)
    for subscription in active:
        categories[subscription.service_category or "Recurring"] += subscription.monthly_amount
    return [
        {
            "category": category,
            "amount": amount,
            "percent": round((amount / total) * 100) if total else 0,
        }
        for category, amount in sorted(categories.items(), key=lambda item: item[1], reverse=True)
    ]


def subscription_opportunities(subscriptions: list[Subscription], limit: int = 5) -> list[dict]:
    candidates = [
        sub
        for sub in subscriptions
        if sub.status not in {"canceled", "ignored"}
        and (sub.replaceable or sub.confidence < 0.78 or sub.monthly_amount >= 40)
    ]
    sorted_candidates = sorted(candidates, key=lambda sub: sub.monthly_amount * savings_multiplier(sub), reverse=True)
    return [{"subscription": sub, "reason": opportunity_reason(sub)} for sub in sorted_candidates[:limit]]


def upcoming_subscriptions(subscriptions: list[Subscription], limit: int = 6) -> list[Subscription]:
    active = [sub for sub in subscriptions if sub.status not in {"canceled", "ignored"}]
    return sorted(active, key=lambda sub: (sub.next_charge_date or date.max, -sub.monthly_amount, sub.name.lower()))[:limit]


def subscription_evidence_map(subscriptions: list[Subscription]) -> dict[int, list[dict]]:
    evidence_by_subscription = {}
    for subscription in subscriptions:
        rows = []
        if subscription.is_manual:
            rows.append(
                {
                    "id": None,
                    "date": subscription.next_charge_date,
                    "description": subscription.name,
                    "amount": subscription.amount,
                }
            )
        else:
            try:
                evidence_items = json.loads(subscription.evidence or "[]")
            except json.JSONDecodeError:
                evidence_items = []
            for item in evidence_items[-6:]:
                rows.append(
                    {
                        "id": item.get("id"),
                        "date": date.fromisoformat(item["date"]) if item.get("date") else None,
                        "description": item.get("description", subscription.name),
                        "amount": item.get("amount", subscription.amount),
                    }
                )
        evidence_by_subscription[subscription.id] = sorted(rows, key=lambda row: row["date"] or date.min, reverse=True)
    return evidence_by_subscription


def average_subscription_confidence(subscriptions: list[Subscription]) -> int:
    if not subscriptions:
        return 0
    return round(sum(sub.confidence for sub in subscriptions) / len(subscriptions) * 100)


def opportunity_reason(subscription: Subscription) -> str:
    if subscription.monthly_amount >= 40:
        return "High monthly cost makes this worth negotiating or canceling."
    if subscription.confidence < 0.78:
        return "Lower confidence means a quick review prevents surprise spend."
    if subscription.replaceable:
        return "Marked as a replaceable service in the catalog."
    return "Recurring spend candidate."


def savings_multiplier(subscription: Subscription) -> float:
    if subscription.status == "review":
        return 1.4
    if subscription.replaceable:
        return 1.2
    return 1


def subscription_summary(db: Session, user: User, *, purpose: str = "subscriptions") -> dict:
    assert_plaid_data_purpose(purpose)
    subscriptions = db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    active = [sub for sub in subscriptions if sub.status not in {"canceled", "ignored"}]
    return {
        "subscriptions": subscriptions,
        "active_count": len(active),
        "review_count": len([sub for sub in subscriptions if sub.status in {"review", "canceling"}]),
        "action_count": len([sub for sub in subscriptions if sub.status == "canceling"]),
        "manage_link_count": len([sub for sub in active if sub.cancel_url]),
        "monthly_total": sum(sub.monthly_amount for sub in active),
        "annual_total": sum(sub.monthly_amount for sub in active) * 12,
        "potential_savings": sum(sub.monthly_amount for sub in active if sub.replaceable or sub.status == "review"),
    }


def parsed_subscription_evidence(subscription: Subscription) -> list[dict]:
    try:
        items = json.loads(subscription.evidence or "[]")
    except json.JSONDecodeError:
        items = []
    return [item for item in items if isinstance(item, dict)]


def refresh_subscription_amounts_from_evidence(subscription: Subscription, evidence_items: list[dict]) -> None:
    cycle = SUBSCRIPTION_CYCLE_OPTIONS.get(subscription.cycle, SUBSCRIPTION_CYCLE_OPTIONS["Monthly"])
    subscription.evidence = json.dumps(evidence_items)
    if not evidence_items:
        subscription.status = "ignored"
        return

    amounts = [abs(parse_amount(item.get("amount") or 0)) for item in evidence_items]
    dates = []
    for item in evidence_items:
        raw_date = item.get("date")
        if not raw_date:
            continue
        try:
            dates.append(date.fromisoformat(raw_date))
        except ValueError:
            continue
    subscription.amount = round(sum(amounts) / len(amounts), 2) if amounts else subscription.amount
    subscription.monthly_amount = round(subscription.amount * cycle["monthly_multiplier"], 2)
    subscription.annual_amount = round(subscription.monthly_amount * 12, 2)
    if dates:
        subscription.first_seen = min(dates)
        subscription.last_seen = max(dates)
        subscription.next_charge_date = subscription.last_seen + timedelta(days=cycle["days"])


def _plaid_post_sync_hook(db: Session, user: User) -> None:
    scan_and_sync_subscriptions(db, user, purpose="subscriptions")


# Flask calls scan_and_sync_subscriptions after Plaid syncs; register the hook
# on import (the subscriptions router imports this module at app startup).
if _plaid_post_sync_hook not in plaid_service.POST_SYNC_HOOKS:
    plaid_service.POST_SYNC_HOOKS.append(_plaid_post_sync_hook)
