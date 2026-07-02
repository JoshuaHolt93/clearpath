# ClearPath Finance Rewrite

Phase 1 monorepo scaffold for the FastAPI auth foundation. The canonical Flask app remains at `C:\Users\joshu\Documents\Codex\ClearPath Finance` and must stay running until cutover.

Current Phase 1 scope:

- Turborepo and pnpm workspace structure.
- FastAPI skeleton under `apps/api`.
- SQLAlchemy 2.x user, household, invite, login-attempt, and onboarding-profile models.
- Alembic migration for the Phase 1 schema.
- JSON auth endpoints with pending-auth MFA state.
- SQLite data-copy script for Phase 1 tables.
- Pytest auth parity coverage.
