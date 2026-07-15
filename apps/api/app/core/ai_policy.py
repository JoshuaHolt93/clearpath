from __future__ import annotations

import re


AI_GUIDANCE_DISCLAIMER = (
    "This is educational financial coaching, not investment, tax, or legal advice. "
    "Consult a licensed professional for personalized advice."
)
AI_GUIDANCE_SANITIZED_BODY = (
    "This guidance was converted to general financial coaching because it may have sounded like "
    "personalized investment advice. Focus on cash flow, emergency savings, debt payoff, "
    "subscriptions, and goals before making specialized financial decisions."
)
AI_GUIDANCE_PROHIBITED_PATTERNS = [
    (
        "securities_ticker",
        re.compile(
            r"\$(?:[A-Z]{1,5})\b|\b(?:AAPL|AMZN|BTC|DOGE|ETH|GOOG|GOOGL|META|MSFT|NVDA|QQQ|SOL|SPY|TSLA|VTI|VOO)\b"
        ),
    ),
    (
        "buy_sell_hold_call",
        re.compile(
            r"\b(?:buy|sell|hold|short|go long|accumulate|dump|trade)\b.{0,80}"
            r"\b(?:stock|etf|fund|crypto|bitcoin|ethereum|portfolio|shares?|[A-Z]{2,5}|\$[A-Z]{1,5})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "portfolio_allocation",
        re.compile(
            r"\b(?:allocate|allocation|portfolio|put|move)\b.{0,80}\b\d{1,3}\s*%(?!\w)|"
            r"\b\d{1,3}\s*%\s+(?:stocks?|bonds?|crypto|equities|etfs?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "performance_prediction",
        re.compile(
            r"\b(?:guaranteed|will|should|expected to|projected to)\b.{0,80}"
            r"\b(?:return|gain|outperform|beat the market|double|rally|moon)\b|"
            r"\b\d{1,3}\s*%\s+(?:annual\s+)?returns?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "market_timing",
        re.compile(
            r"\b(?:time the market|buy the dip|market bottom|market top|before earnings|"
            r"after earnings|buy now|sell now|rotate into|rotate out of)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "individualized_investment_recommendation",
        re.compile(
            r"\b(?:you should|i recommend|best for you|right for you)\b.{0,120}"
            r"\b(?:investment|brokerage|ira|roth|401k|hsa|529|fund|etf|stock|bond|crypto|securities)\b",
            re.IGNORECASE,
        ),
    ),
]


class AIInvestmentAdviceError(RuntimeError):
    pass


def ai_guidance_policy_violations(text: str | None) -> list[str]:
    content = str(text or "")
    return sorted(
        {
            violation_type
            for violation_type, pattern in AI_GUIDANCE_PROHIBITED_PATTERNS
            if pattern.search(content)
        }
    )


def ai_guidance_allowed(text: str | None) -> bool:
    return not ai_guidance_policy_violations(text)


def assert_ai_guidance_allowed(text: str | None) -> str:
    violations = ai_guidance_policy_violations(text)
    if violations:
        raise AIInvestmentAdviceError(
            "AI guidance content is outside ClearPath's coaching-only scope: "
            + ", ".join(violations)
        )
    return str(text or "")


def sanitize_ai_guidance_text(text: str | None) -> str:
    content = str(text or "")
    return content if ai_guidance_allowed(content) else AI_GUIDANCE_SANITIZED_BODY


def guardrail_ai_guidance_item(item: dict) -> dict:
    guarded = dict(item)
    title = str(guarded.get("title") or "")
    body = str(guarded.get("body") or "")
    violations = sorted(
        set(ai_guidance_policy_violations(title) + ai_guidance_policy_violations(body))
    )
    if violations:
        guarded["title"] = "General Financial Coaching"
        guarded["body"] = AI_GUIDANCE_SANITIZED_BODY
        guarded["level"] = "info"
        guarded["type"] = guarded.get("type") or "coaching_guardrail"
        guarded["guardrail_violations"] = violations
    guarded["disclaimer"] = AI_GUIDANCE_DISCLAIMER
    return guarded


def guardrail_ai_guidance_items(items: list[dict]) -> list[dict]:
    return [guardrail_ai_guidance_item(item) for item in items]
