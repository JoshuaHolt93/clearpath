from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import Settings, get_settings

RESEND_USER_AGENT = "ClearPathFinance/1.0 (+https://www.clear-path-finance.com)"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    sent: bool
    reason: str = ""


def configured_sender(settings: Settings | None = None) -> str | None:
    settings = settings or get_settings()
    return settings.transactional_email_from or settings.mail_default_sender or settings.mail_username


def email_delivery_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(configured_sender(settings) and (settings.resend_api_key or settings.mail_server))


def deliver_household_invite_email(invite, invite_url: str) -> EmailDeliveryResult:
    # Flask household_access.deliver_household_invite_email at 92ccdbc.
    if not email_delivery_configured():
        return EmailDeliveryResult(False, "not_configured")

    owner = invite.owner_user
    household_name = owner.household_name or "a ClearPath household"
    role_labels = {"editor": "Can Edit", "viewer": "View Only"}
    role_label = role_labels.get((invite.role or "").strip().lower(), "Can Edit")
    return send_transactional_email(
        to_email=invite.email,
        subject=f"You have been invited to {household_name} on ClearPath Finance",
        text_body=(
            f"{owner.email} invited you to join {household_name} on ClearPath Finance.\n\n"
            f"Permission: {role_label}\n"
            "Use this secure link to create your own shared-access password. "
            "The link expires in 14 days and can only be used once.\n\n"
            f"{invite_url}\n\n"
            "If you were not expecting this invite, you can ignore this email."
        ),
    )


def send_transactional_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    settings: Settings | None = None,
) -> EmailDeliveryResult:
    settings = settings or get_settings()
    sender = configured_sender(settings)
    if not sender:
        return EmailDeliveryResult(False, "missing_sender")
    if settings.resend_api_key:
        return _send_resend_email(
            sender=sender,
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            settings=settings,
        )
    if settings.mail_server:
        return _send_smtp_email(
            sender=sender,
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            settings=settings,
        )
    return EmailDeliveryResult(False, "missing_provider")


def send_password_reset_email(*, to_email: str, reset_url: str) -> EmailDeliveryResult:
    return send_transactional_email(
        to_email=to_email,
        subject="Reset your ClearPath Finance password",
        text_body=(
            "Use this link to reset your ClearPath Finance password. "
            "The link expires in 30 minutes and can only be used once.\n\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
    )


def _send_resend_email(
    *,
    sender: str,
    to_email: str,
    subject: str,
    text_body: str,
    settings: Settings,
) -> EmailDeliveryResult:
    payload = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": text_body,
    }
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": RESEND_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 200 <= response.status < 300:
                return EmailDeliveryResult(True)
            logger.error(
                "Transactional email provider returned status %s: %s.",
                response.status,
                _provider_response_summary(response.read()),
            )
            return EmailDeliveryResult(False, f"provider_status_{response.status}")
    except urllib.error.HTTPError as exc:
        logger.error(
            "Transactional email provider returned status %s: %s.",
            exc.code,
            _provider_response_summary(exc.read()),
        )
        return EmailDeliveryResult(False, f"provider_status_{exc.code}")
    except Exception:
        logger.exception("Transactional email provider request failed.")
        return EmailDeliveryResult(False, "provider_error")


def _provider_response_summary(raw_body: bytes | str | None) -> str:
    if not raw_body:
        return "empty_response"
    text = raw_body.decode("utf-8", errors="replace") if isinstance(raw_body, bytes) else raw_body
    collapsed = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return collapsed[:500] or "empty_response"


def _send_smtp_email(
    *,
    sender: str,
    to_email: str,
    subject: str,
    text_body: str,
    settings: Settings,
) -> EmailDeliveryResult:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(text_body)

    try:
        if settings.mail_use_ssl:
            smtp_context = smtplib.SMTP_SSL(settings.mail_server, settings.mail_port, timeout=15)
        else:
            smtp_context = smtplib.SMTP(settings.mail_server, settings.mail_port, timeout=15)
        with smtp_context as smtp:
            if settings.mail_use_tls and not settings.mail_use_ssl:
                smtp.starttls()
            if settings.mail_username and settings.mail_password:
                smtp.login(settings.mail_username, settings.mail_password)
            smtp.send_message(message)
        return EmailDeliveryResult(True)
    except Exception:
        logger.exception("SMTP transactional email failed.")
        return EmailDeliveryResult(False, "smtp_error")
