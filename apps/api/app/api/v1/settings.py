from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.planning_constants import ACCOUNT_CLASSIFICATION_OPTIONS
from app.core.security import password_policy_errors
from app.dependencies import Principal, require_household_access, require_primary_account_holder
from app.models import HouseholdInvite, HouseholdMember, utc_now
from app.schemas.settings import (
    AccountDeleteRequest,
    AccountDeleteResponse,
    CategoryManagerRowResponse,
    EthicsAcknowledgementRequest,
    EthicsAcknowledgementResponse,
    HouseholdInviteCreateRequest,
    HouseholdInviteCreateResponse,
    HouseholdInviteResponse,
    HouseholdInviteRevokeRequest,
    HouseholdMemberResponse,
    HouseholdMemberRevokeRequest,
    HouseholdMemberRoleUpdateRequest,
    HouseholdResponse,
    HouseholdUpdateRequest,
    MfaPreferenceResponse,
    MfaPreferenceUpdateRequest,
    PasswordChangeRequest,
    PasswordChangeResponse,
    SettingsDashboardResponse,
)
from app.schemas.transactions import CategoryResponse
from app.services.auth_service import (
    ETHICS_POLICY_VERSION,
    HOUSEHOLD_ROLE_EDITOR,
    HOUSEHOLD_ROLE_VIEWER,
    create_household_invite,
    normalize_household_role,
)
from app.services.billing_service import billing_status
from app.services.email_service import deliver_household_invite_email
from app.services.feedback_service import feedback_form_options
from app.services.mfa_push_service import push_mfa_available, push_mfa_status
from app.services.plaid_service import plaid_status
from app.services.settings_service import (
    ACCOUNT_DELETE_CONFIRMATION,
    account_delete_requires_billing_cancellation,
    delete_user_account_data,
)
from app.services.transaction_service import (
    CategoryRule,
    category_manager_rows_for_user,
    merge_duplicate_categories,
    require_onboarding_complete,
)

router = APIRouter(tags=["settings"])

HOUSEHOLD_ROLE_OPTIONS = {
    HOUSEHOLD_ROLE_EDITOR: "Can Edit",
    HOUSEHOLD_ROLE_VIEWER: "View Only",
}


def _member_for_owner(db: Session, owner_id: int, member_id: int) -> HouseholdMember:
    member = db.scalar(select(HouseholdMember).where(HouseholdMember.id == member_id, HouseholdMember.owner_user_id == owner_id))
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household member not found.")
    return member


@router.get("/me/settings", response_model=SettingsDashboardResponse)
def get_settings_dashboard(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> SettingsDashboardResponse:
    user = principal.user
    require_onboarding_complete(user)
    merge_duplicate_categories(db)
    category_rows = [
        CategoryManagerRowResponse(
            category=CategoryResponse.model_validate(row["category"]),
            usage=row["usage"],
            can_manage=row["can_manage"],
        )
        for row in category_manager_rows_for_user(db, user)
    ]
    rules_count = db.query(CategoryRule).filter_by(user_id=user.id).count()
    members = db.scalars(
        select(HouseholdMember).where(HouseholdMember.owner_user_id == user.id).order_by(HouseholdMember.created_at.desc())
    ).all()
    pending_invites = db.scalars(
        select(HouseholdInvite)
        .where(HouseholdInvite.owner_user_id == user.id, HouseholdInvite.status == "pending")
        .order_by(HouseholdInvite.created_at.desc())
    ).all()
    return SettingsDashboardResponse(
        email=user.email,
        display_name=user.display_name,
        household_name=user.household_name,
        category_rows=category_rows,
        rules_count=rules_count,
        plaid_status=plaid_status(),
        push_mfa=push_mfa_status(),
        mfa_preferred_method=user.mfa_preferred_method,
        mfa_push_enabled=user.mfa_push_enabled,
        billing_status=billing_status(),
        feedback_options=feedback_form_options(),
        household_role_options=HOUSEHOLD_ROLE_OPTIONS,
        household_members=[HouseholdMemberResponse.model_validate(member) for member in members],
        pending_household_invites=[HouseholdInviteResponse.model_validate(invite) for invite in pending_invites],
        can_manage_household_access=not principal.is_shared_session,
        household_access_is_shared=principal.is_shared_session,
        ethics_acknowledged_at=user.ethics_acknowledged_at,
        ethics_policy_version=user.ethics_policy_version,
        account_delete_confirmation=ACCOUNT_DELETE_CONFIRMATION,
        account_delete_billing_blocked=account_delete_requires_billing_cancellation(user),
        account_classification_options=list(ACCOUNT_CLASSIFICATION_OPTIONS),
    )


@router.patch("/me/password", response_model=PasswordChangeResponse)
def change_password(
    payload: PasswordChangeRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> PasswordChangeResponse:
    user = principal.user
    errors = password_policy_errors(payload.new_password, user.email)
    if not user.check_password(payload.current_password):
        raise HTTPException(status_code=422, detail="Current password was incorrect.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="New password and confirmation did not match.")
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))
    user.set_password(payload.new_password)
    db.commit()
    return PasswordChangeResponse(updated=True)


@router.patch("/households/current", response_model=HouseholdResponse)
def update_household(
    payload: HouseholdUpdateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdResponse:
    # Flask settings action=household stores the stripped value verbatim
    # (including an empty string).
    principal.user.household_name = (payload.household_name or "").strip()
    db.commit()
    return HouseholdResponse(household_name=principal.user.household_name)


@router.patch("/auth/mfa/preferences", response_model=MfaPreferenceResponse)
def update_mfa_preferences(
    payload: MfaPreferenceUpdateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> MfaPreferenceResponse:
    user = principal.user
    requested_method = payload.mfa_preferred_method or "totp"
    if requested_method == "push" and push_mfa_available():
        user.mfa_push_enabled = True
        user.mfa_preferred_method = "push"
        message = "Duo Push approval will be used when you sign in, with authenticator codes as a fallback."
    elif requested_method == "push":
        user.mfa_push_enabled = False
        user.mfa_preferred_method = "totp"
        message = "Push approval is not configured yet. Authenticator codes remain active."
    else:
        user.mfa_push_enabled = False
        user.mfa_preferred_method = "totp"
        message = "Authenticator codes will be used when you sign in."
    db.commit()
    return MfaPreferenceResponse(
        mfa_preferred_method=user.mfa_preferred_method,
        mfa_push_enabled=user.mfa_push_enabled,
        push=push_mfa_status(),
        message=message,
    )


@router.delete("/me/account", response_model=AccountDeleteResponse)
def delete_account(
    payload: AccountDeleteRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> AccountDeleteResponse:
    user = principal.user
    if account_delete_requires_billing_cancellation(user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel your active Stripe subscription first, then return here to delete the ClearPath account data.",
        )
    if not user.check_password(payload.current_password):
        raise HTTPException(status_code=422, detail="Current password was incorrect.")
    if (payload.confirmation or "").strip() != ACCOUNT_DELETE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Type {ACCOUNT_DELETE_CONFIRMATION} to confirm account deletion.")
    delete_user_account_data(db, user)
    db.commit()
    return AccountDeleteResponse(deleted=True)


@router.post("/me/compliance-acknowledgements/ethics", response_model=EthicsAcknowledgementResponse)
def acknowledge_ethics_policy(
    payload: EthicsAcknowledgementRequest,
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> EthicsAcknowledgementResponse:
    user = principal.user
    user.ethics_acknowledged_at = utc_now()
    user.ethics_policy_version = ETHICS_POLICY_VERSION
    db.commit()
    return EthicsAcknowledgementResponse(
        ethics_acknowledged_at=user.ethics_acknowledged_at,
        ethics_policy_version=user.ethics_policy_version,
    )


@router.post("/households/current/invites", response_model=HouseholdInviteCreateResponse, status_code=status.HTTP_201_CREATED)
def create_invite_endpoint(
    payload: HouseholdInviteCreateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdInviteCreateResponse:
    user = principal.user
    try:
        invite, token = create_household_invite(db, user, payload.invite_email, normalize_household_role(payload.invite_role))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    web_base = (get_settings().web_app_url or "").rstrip("/")
    invite_url = f"{web_base}/household/invite/{token}" if web_base else f"/household/invite/{token}"
    delivery = deliver_household_invite_email(invite, invite_url)
    return HouseholdInviteCreateResponse(
        invite=HouseholdInviteResponse.model_validate(invite),
        email_sent=delivery.sent,
        fallback_invite_url=None if delivery.sent else invite_url,
        delivery_reason=None if delivery.sent else delivery.reason,
    )


@router.patch("/households/current/members/{member_id}", response_model=HouseholdMemberResponse)
def update_member_role(
    member_id: int,
    payload: HouseholdMemberRoleUpdateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdMemberResponse:
    member = _member_for_owner(db, principal.user.id, member_id)
    member.role = normalize_household_role(payload.member_role)
    db.commit()
    return HouseholdMemberResponse.model_validate(member)


@router.delete("/households/current/members/{member_id}", response_model=HouseholdMemberResponse)
def revoke_member(
    member_id: int,
    payload: HouseholdMemberRevokeRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdMemberResponse:
    member = _member_for_owner(db, principal.user.id, member_id)
    member.status = "revoked"
    db.commit()
    return HouseholdMemberResponse.model_validate(member)


@router.delete("/households/current/invites/{invite_id}", response_model=HouseholdInviteResponse)
def revoke_invite(
    invite_id: int,
    payload: HouseholdInviteRevokeRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdInviteResponse:
    invite = db.scalar(select(HouseholdInvite).where(HouseholdInvite.id == invite_id, HouseholdInvite.owner_user_id == principal.user.id))
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household invite not found.")
    invite.status = "revoked"
    invite.revoked_at = utc_now()
    db.commit()
    return HouseholdInviteResponse.model_validate(invite)
