from __future__ import annotations

import typer
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PlaidItem, User

cli = typer.Typer(help="ClearPath Finance operational CLI.")


@cli.command("seed-demo")
def seed_demo() -> None:
    from app.services.seed_service import DEMO_EMAIL, seed_demo_user

    with SessionLocal() as db:
        user = seed_demo_user(db)
    if user is None:
        typer.echo(f"Demo user {DEMO_EMAIL} already exists; nothing to seed.")
    else:
        typer.echo(f"Seeded demo account {DEMO_EMAIL}.")


@cli.command("seed-defaults")
def seed_defaults() -> None:
    from app.services.seed_service import ensure_defaults

    with SessionLocal() as db:
        ensure_defaults(db)
    typer.echo("Seeded default categories.")


@cli.command("make-admin")
def make_admin(email: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if not user:
            typer.echo("User not found.", err=True)
            raise typer.Exit(1)
        user.is_admin = True
        db.commit()
        typer.echo(f"Admin access granted to {user.email}.")


@cli.command("sync-live-bank-data")
def sync_live_bank_data(
    user_id: int | None = typer.Option(None),
    plaid_item_id: int | None = typer.Option(None),
    all_users: bool = typer.Option(False),
) -> None:
    # Faithful port of Flask jobs.sync_live_bank_data at 92ccdbc: requires an
    # explicit target, complete Plaid configuration, and runs the same
    # post-sync subscription/monthly-plan hooks per synced user.
    from app.services.plaid_service import (
        PlaidConfigurationError,
        PlaidRequestError,
        plaid_status,
        run_post_sync_hooks,
        sync_plaid_item,
    )

    if not all_users and user_id is None and plaid_item_id is None:
        typer.echo("sync-live-bank-data requires --user-id, --plaid-item-id, or --all-users.", err=True)
        raise typer.Exit(1)
    if not plaid_status().get("ready", False):
        typer.echo("Plaid is not fully configured. Check PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_TOKEN_ENCRYPTION_KEY.", err=True)
        raise typer.Exit(1)

    with SessionLocal() as db:
        if plaid_item_id is not None:
            item_query = select(PlaidItem).where(PlaidItem.id == plaid_item_id, PlaidItem.status == "connected")
            if user_id is not None:
                item_query = item_query.where(PlaidItem.user_id == user_id)
            plaid_item = db.scalar(item_query)
            users = [db.get(User, plaid_item.user_id)] if plaid_item else []
        elif user_id is not None:
            user = db.get(User, user_id)
            users = [user] if user else []
        else:
            users = list(
                db.scalars(
                    select(User).join(PlaidItem, PlaidItem.user_id == User.id).where(PlaidItem.status == "connected").distinct()
                ).all()
            )

        synced = 0
        errors: list[str] = []
        for user in users:
            user_synced = False
            item_query = select(PlaidItem).where(PlaidItem.user_id == user.id, PlaidItem.status == "connected")
            if plaid_item_id is not None:
                item_query = item_query.where(PlaidItem.id == plaid_item_id)
            for plaid_item in db.scalars(item_query).all():
                try:
                    sync_plaid_item(db, plaid_item, purpose="account_sync")
                except (PlaidConfigurationError, PlaidRequestError) as exc:
                    errors.append(f"{user.email}: {exc}")
                else:
                    synced += 1
                    user_synced = True
            if user_synced:
                run_post_sync_hooks(db, user)

    typer.echo(f"Synced {synced} Plaid item(s).")
    for error in errors:
        typer.echo(f"error: {error}", err=True)
    if errors and not synced:
        raise typer.Exit(1)


@cli.command("run-control-evaluations")
def run_control_evaluations() -> None:
    from app.main import create_app
    from app.services.compliance_service import run_control_evaluations as run_evaluations

    app = create_app()
    with SessionLocal() as db:
        result = run_evaluations(db, app)
    typer.echo(f"Recorded {result['evaluated']} SOC2 CC4.1 control evaluation results.")
    for row in result["results"]:
        typer.echo(f"{row['control_id']}: {row['status']} - {row['evidence']}")


def main() -> None:
    """Console-script entry point declared in pyproject as `clearpath`."""
    cli()


if __name__ == "__main__":
    main()
