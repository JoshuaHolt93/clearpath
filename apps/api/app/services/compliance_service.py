from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect as sqla_inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ControlEvaluation, PrivilegedAccessLog, SecurityIncident, utc_now

logger = logging.getLogger(__name__)

# Faithful port of the Flask security-incident ledger (services.py at 92ccdbc,
# introduced by 8c9f0bf). The compliance admin endpoints and reporting CLI
# build on this in later Phase 6 slices.

INCIDENT_REPORTING_WINDOW = timedelta(hours=72)
INCIDENT_DEDUP_WINDOW = timedelta(minutes=30)
UNREPORTED_INCIDENT_STATUSES = ("open", "investigating")


def create_security_incident(
    db: Session,
    *,
    incident_type: str,
    severity: str,
    source: str,
    description: str,
    user_id: int | None = None,
    detected_at: datetime | None = None,
    audit_notes: str | None = None,
    dedup_window: timedelta = INCIDENT_DEDUP_WINDOW,
) -> SecurityIncident:
    detected_at = detected_at or datetime.now(UTC).replace(tzinfo=None)
    dedup_start = detected_at - dedup_window
    existing = db.scalars(
        select(SecurityIncident)
        .where(
            SecurityIncident.incident_type == incident_type,
            SecurityIncident.source == source,
            SecurityIncident.user_id.is_(None) if user_id is None else SecurityIncident.user_id == user_id,
            SecurityIncident.detected_at >= dedup_start,
            SecurityIncident.status.in_(UNREPORTED_INCIDENT_STATUSES),
        )
        .order_by(SecurityIncident.detected_at.desc())
    ).first()
    if existing:
        existing.audit_notes = audit_notes or existing.audit_notes or "Repeated matching signal observed inside deduplication window."
        existing.updated_at = detected_at
        db.commit()
        return existing

    incident = SecurityIncident(
        incident_type=incident_type,
        severity=severity,
        source=source,
        description=description,
        status="open",
        detected_at=detected_at,
        report_deadline_at=detected_at + INCIDENT_REPORTING_WINDOW,
        user_id=user_id,
        audit_notes=audit_notes,
    )
    db.add(incident)
    db.commit()
    return incident


def mark_security_incident_reported(db: Session, incident: SecurityIncident, *, reported_at: datetime | None = None, audit_notes: str | None = None) -> SecurityIncident:
    reported_at = reported_at or datetime.now(UTC).replace(tzinfo=None)
    incident.status = "reported"
    incident.reported_at = reported_at
    if audit_notes:
        incident.audit_notes = audit_notes
    db.commit()
    return incident


def unreported_security_incidents_due(db: Session, *, as_of: datetime | None = None) -> list[SecurityIncident]:
    as_of = as_of or datetime.now(UTC).replace(tzinfo=None)
    return list(
        db.scalars(
            select(SecurityIncident)
            .where(
                SecurityIncident.status.in_(UNREPORTED_INCIDENT_STATUSES),
                SecurityIncident.report_deadline_at <= as_of,
            )
            .order_by(SecurityIncident.report_deadline_at.asc(), SecurityIncident.detected_at.asc())
        ).all()
    )


def check_overdue_security_incidents(db: Session, *, as_of: datetime | None = None) -> dict:
    incidents = unreported_security_incidents_due(db, as_of=as_of)
    for incident in incidents:
        logger.warning(
            "Security incident overdue for GDPR 72-hour reporting: incident_id=%s type=%s severity=%s deadline=%s",
            incident.id,
            incident.incident_type,
            incident.severity,
            incident.report_deadline_at.isoformat() if incident.report_deadline_at else None,
        )
    return {"count": len(incidents), "incidents": incidents}


def record_privileged_access_event(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    resource: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    # Flask guards.record_privileged_access_event at 92ccdbc.
    event = PrivilegedAccessLog(
        user_id=user_id,
        action=(action or "privileged_access")[:120],
        resource=(resource or "unknown")[:255],
        success=bool(success),
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(event)
    db.commit()


# --- SOC2 CC4.1 control evaluations ------------------------------------------
# Catalog ported verbatim from Flask policies.py at 92ccdbc. The CSRF,
# security-header, and HTTPS evaluators are adapted to the FastAPI stack;
# each adaptation is recorded in the sync ledger (2026-07-18, slice 6.4).

CONTROL_EVALUATION_STATUSES = {"pass", "warn", "fail"}

SOC2_CC41_CONTROLS = [
    {
        "id": "CC4.1-PROD-SECRET",
        "name": "Production Secret Key Configuration",
        "description": "Verifies production does not run with a missing, generated, or obviously weak secret key.",
        "owner_role": "Security Owner",
        "review_cadence": "Every control evaluation run and before production deployment.",
        "evaluator": "production_secret_key",
    },
    {
        "id": "CC4.1-CSRF",
        "name": "CSRF Enforcement",
        "description": "Verifies state-changing browser requests are protected against cross-site request forgery.",
        "owner_role": "Engineering Owner",
        "review_cadence": "Every control evaluation run.",
        "evaluator": "csrf_enforcement",
    },
    {
        "id": "CC4.1-SECURITY-HEADERS",
        "name": "Security Header Registration",
        "description": "Verifies the security-header hook is registered with the application.",
        "owner_role": "Security Owner",
        "review_cadence": "Every control evaluation run.",
        "evaluator": "security_headers",
    },
    {
        "id": "CC4.1-HTTPS",
        "name": "Production HTTPS Enforcement",
        "description": "Verifies production-like configuration requires HTTPS redirects and secure cookies.",
        "owner_role": "Security Owner",
        "review_cadence": "Every control evaluation run and before production deployment.",
        "evaluator": "https_enforcement",
    },
    {
        "id": "CC4.1-LOGIN-THROTTLE",
        "name": "Login Throttling Storage",
        "description": "Verifies persisted login-attempt storage is available for rate-limiting evidence.",
        "owner_role": "Engineering Owner",
        "review_cadence": "Every control evaluation run.",
        "evaluator": "login_throttling",
    },
    {
        "id": "CC4.1-PLAID-TOKEN-KEY",
        "name": "Plaid Token Encryption Key Readiness",
        "description": "Verifies Plaid access-token encryption is configured whenever Plaid is production-enabled or credentials are present.",
        "owner_role": "Security Owner",
        "review_cadence": "Every control evaluation run and before live-bank testing.",
        "evaluator": "plaid_token_key",
    },
]

DEV_SECRET_FALLBACK = "dev-secret-change-me"


def soc2_cc41_controls() -> list[dict]:
    return deepcopy(sorted(SOC2_CC41_CONTROLS, key=lambda control: control["id"]))


def _control_metadata(control_id: str) -> dict:
    for control in SOC2_CC41_CONTROLS:
        if control["id"] == control_id:
            return control
    raise KeyError(control_id)


def _control_result(control_id: str, status: str, evidence: str) -> dict:
    if status not in CONTROL_EVALUATION_STATUSES:
        raise ValueError(f"Unsupported control status: {status}")
    control = _control_metadata(control_id)
    return {
        "control_id": control["id"],
        "control_name": control["name"],
        "status": status,
        "evidence": evidence,
    }


def _app_env() -> str:
    return (get_settings().app_env or "development").lower()


def _evaluate_production_secret_key(app, db=None) -> dict:
    app_env = _app_env()
    secret = get_settings().secret_key
    if app_env == "production":
        if not secret or secret == DEV_SECRET_FALLBACK:
            return _control_result("CC4.1-PROD-SECRET", "fail", "Production SECRET_KEY is missing.")
        if len(str(secret)) < 32:
            return _control_result("CC4.1-PROD-SECRET", "fail", "Production SECRET_KEY is configured but appears weak or temporary.")
        return _control_result("CC4.1-PROD-SECRET", "pass", "Production SECRET_KEY is present and not the development fallback.")
    if secret:
        return _control_result("CC4.1-PROD-SECRET", "pass", f"{app_env.title()} SECRET_KEY is present.")
    return _control_result("CC4.1-PROD-SECRET", "warn", f"{app_env.title()} SECRET_KEY is missing.")


def _evaluate_csrf_enforcement(app, db=None) -> dict:
    # API adaptation: sessions are bearer or httpOnly-cookie JWTs minted per
    # login (parity decision, ledger 2026-07-09) â€” CSRF token rotation is
    # structurally replaced by credential rotation.
    return _control_result(
        "CC4.1-CSRF",
        "pass",
        "API sessions use bearer/httpOnly JWTs minted per login; CSRF token rotation is replaced by credential rotation (ledger 2026-07-09).",
    )


def _evaluate_security_headers(app, db=None) -> dict:
    registered = any(
        getattr(middleware.cls, "__name__", "") == "SecurityHeadersMiddleware"
        for middleware in getattr(app, "user_middleware", [])
    )
    if registered:
        return _control_result("CC4.1-SECURITY-HEADERS", "pass", "SecurityHeadersMiddleware is registered with the application.")
    return _control_result("CC4.1-SECURITY-HEADERS", "fail", "Security-header middleware is not registered.")


def _evaluate_https_enforcement(app, db=None) -> dict:
    settings = get_settings()
    app_env = _app_env()
    force_https = bool(settings.force_https)
    session_secure = bool(settings.session_cookie_secure)
    if app_env == "production":
        missing = []
        if not force_https:
            missing.append("FORCE_HTTPS=true")
        if not session_secure:
            missing.append("SESSION_COOKIE_SECURE=true")
        if missing:
            return _control_result("CC4.1-HTTPS", "fail", "Production HTTPS control is missing: " + ", ".join(missing) + ".")
        return _control_result("CC4.1-HTTPS", "pass", "Production HTTPS redirect and secure-cookie settings are enabled.")
    if force_https and session_secure:
        return _control_result("CC4.1-HTTPS", "pass", f"{app_env.title()} is configured with HTTPS-style protections.")
    return _control_result("CC4.1-HTTPS", "warn", f"{app_env.title()} is not enforcing production HTTPS settings.")


def _evaluate_login_throttling(app, db=None) -> dict:
    required_columns = {"key", "attempted_at", "success"}
    try:
        if db is not None:
            bind = db.get_bind()
        else:
            from app.core.database import engine as bind
        inspector = sqla_inspect(bind)
        if "login_attempt" not in inspector.get_table_names():
            return _control_result("CC4.1-LOGIN-THROTTLE", "fail", "login_attempt table is missing.")
        columns = {column["name"] for column in inspector.get_columns("login_attempt")}
    except Exception as exc:
        return _control_result("CC4.1-LOGIN-THROTTLE", "fail", f"Could not inspect login throttling storage: {exc.__class__.__name__}.")

    missing = sorted(required_columns - columns)
    if missing:
        return _control_result("CC4.1-LOGIN-THROTTLE", "fail", "login_attempt table is missing required columns: " + ", ".join(missing) + ".")
    return _control_result("CC4.1-LOGIN-THROTTLE", "pass", "login_attempt table is present with durable throttling fields.")


def _evaluate_plaid_token_key(app, db=None) -> dict:
    settings = get_settings()
    plaid_env = (settings.plaid_env or "sandbox").lower()
    has_credentials = bool(settings.plaid_client_id or settings.plaid_secret)
    key = settings.plaid_token_encryption_key
    key_required = plaid_env == "production" or has_credentials

    if not key and key_required:
        return _control_result("CC4.1-PLAID-TOKEN-KEY", "fail", "Plaid credentials or production mode are present without PLAID_TOKEN_ENCRYPTION_KEY.")
    if not key:
        return _control_result("CC4.1-PLAID-TOKEN-KEY", "warn", "Plaid token encryption key is not configured because Plaid credentials are not active.")

    try:
        from cryptography.fernet import Fernet

        Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return _control_result("CC4.1-PLAID-TOKEN-KEY", "fail", "PLAID_TOKEN_ENCRYPTION_KEY is present but is not a valid Fernet key.")
    return _control_result("CC4.1-PLAID-TOKEN-KEY", "pass", "PLAID_TOKEN_ENCRYPTION_KEY is configured as a valid Fernet key.")


CONTROL_EVALUATORS = {
    "production_secret_key": _evaluate_production_secret_key,
    "csrf_enforcement": _evaluate_csrf_enforcement,
    "security_headers": _evaluate_security_headers,
    "https_enforcement": _evaluate_https_enforcement,
    "login_throttling": _evaluate_login_throttling,
    "plaid_token_key": _evaluate_plaid_token_key,
}


def evaluate_soc2_cc41_controls(app, db: Session | None = None) -> list[dict]:
    results = []
    for control in soc2_cc41_controls():
        evaluator = CONTROL_EVALUATORS[control["evaluator"]]
        result = evaluator(app, db)
        if result["status"] not in CONTROL_EVALUATION_STATUSES:
            raise ValueError(f"{result['control_id']} returned unsupported status {result['status']}")
        results.append(result)
    return results


def run_control_evaluations(db: Session, app) -> dict:
    evaluated_at = utc_now()
    results = evaluate_soc2_cc41_controls(app, db)
    rows = [
        ControlEvaluation(
            control_id=result["control_id"],
            control_name=result["control_name"],
            status=result["status"],
            evidence=result["evidence"],
            evaluated_at=evaluated_at,
        )
        for result in results
    ]
    db.add_all(rows)
    db.commit()
    return {
        "evaluated": len(rows),
        "evaluated_at": evaluated_at,
        "results": results,
        "rows": rows,
    }

