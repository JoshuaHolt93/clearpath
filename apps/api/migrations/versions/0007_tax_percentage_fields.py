"""additional tax percentage worksheet fields

Revision ID: 0007_tax_percentage_fields
Revises: 0006_tax_additional_fields
Create Date: 2026-07-12

Mirrors Flask migration e2f3a4b (commit 64b5ed5): the additional local
tax can be entered as a flat monthly amount or a percentage of gross.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_tax_percentage_fields"
down_revision = "0006_tax_additional_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("onboarding_profile") as batch_op:
        batch_op.add_column(sa.Column("tax_additional_type", sa.String(length=20), nullable=False, server_default="amount"))
        batch_op.add_column(sa.Column("tax_additional_rate", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("onboarding_profile") as batch_op:
        batch_op.drop_column("tax_additional_rate")
        batch_op.drop_column("tax_additional_type")
