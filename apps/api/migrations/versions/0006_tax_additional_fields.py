"""additional local tax fields on onboarding profile

Revision ID: 0006_tax_additional_fields
Revises: 0005_phase3_planning
Create Date: 2026-07-10

Mirrors Flask migration d0c1d2e3f4a (commit 40cf107): the onboarding
profile gains a user-labeled additional local tax with a monthly amount.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_tax_additional_fields"
down_revision = "0005_phase3_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("onboarding_profile") as batch_op:
        batch_op.add_column(
            sa.Column("tax_additional_label", sa.String(length=80), nullable=False, server_default="Additional Local Tax")
        )
        batch_op.add_column(
            sa.Column("tax_additional_monthly_amount", sa.Float(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("onboarding_profile") as batch_op:
        batch_op.drop_column("tax_additional_monthly_amount")
        batch_op.drop_column("tax_additional_label")
