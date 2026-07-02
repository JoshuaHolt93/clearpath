from __future__ import annotations

from app.core.defaults import REGISTRATION_DEFAULT_PAYCHECK_CADENCE, SCHEMA_DEFAULT_PAYCHECK_CADENCE
from app.models import OnboardingProfile, User
from app.services.auth_service import create_default_profile


def test_paycheck_cadence_defaults_preserve_flask_parity():
    assert OnboardingProfile.__table__.c.paycheck_cadence.default.arg == SCHEMA_DEFAULT_PAYCHECK_CADENCE

    user = User(email="owner@example.com", password_hash="hash")
    profile = create_default_profile(user)

    assert profile.income_frequency == REGISTRATION_DEFAULT_PAYCHECK_CADENCE
    assert profile.paycheck_cadence == REGISTRATION_DEFAULT_PAYCHECK_CADENCE
