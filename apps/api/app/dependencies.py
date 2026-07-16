from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models import HouseholdMember, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user: User
    subject: User | HouseholdMember
    subject_type: str
    subject_id: int
    household_member: HouseholdMember | None
    household_role: str | None
    mfa_verified: bool
    stay_signed_in: bool

    @property
    def is_shared_session(self) -> bool:
        return self.household_member is not None


def _token_from_request(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return request.cookies.get(get_settings().session_cookie_name)


def get_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    token = _token_from_request(request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.") from exc
    if payload.get("type") != "session":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session type.")

    user = db.get(User, int(payload["user_id"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session user no longer exists.")

    household_member = None
    subject: User | HouseholdMember = user
    subject_type = payload.get("subject_type") or "user"
    subject_id = int(payload.get("subject_id") or user.id)
    if payload.get("household_member_id"):
        household_member = db.get(HouseholdMember, int(payload["household_member_id"]))
        if not household_member or household_member.status != "active" or household_member.owner_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Shared household access is no longer active.")
        subject = household_member
        subject_type = "household_member"
        subject_id = household_member.id

    return Principal(
        user=user,
        subject=subject,
        subject_type=subject_type,
        subject_id=subject_id,
        household_member=household_member,
        household_role=payload.get("household_role"),
        mfa_verified=bool(payload.get("mfa_verified")),
        stay_signed_in=bool(payload.get("stay_signed_in")),
    )


def require_full_session(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not principal.mfa_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA verification is required.")
    return principal


def require_pending_auth(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.mfa_verified:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already complete.")
    return principal


def require_primary_account_holder(principal: Annotated[Principal, Depends(require_full_session)]) -> Principal:
    if principal.is_shared_session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Primary account holder access is required.")
    return principal


def require_household_access(min_role: str = "viewer") -> Callable[[Principal], Principal]:
    def dependency(principal: Annotated[Principal, Depends(require_full_session)]) -> Principal:
        if not principal.is_shared_session:
            return principal
        role = (principal.household_member.role if principal.household_member else principal.household_role) or "editor"
        if min_role == "viewer" and role in {"viewer", "editor"}:
            return principal
        if min_role == "editor" and role == "editor":
            return principal
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shared household access is view-only.")

    return dependency
