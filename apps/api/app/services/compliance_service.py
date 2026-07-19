from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SecurityIncident

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
