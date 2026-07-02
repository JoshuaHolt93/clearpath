from __future__ import annotations

import typer
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User

cli = typer.Typer(help="ClearPath Finance operational CLI.")


def _phase_not_ported(command: str, phase: str) -> None:
    typer.echo(f"{command} is registered but its underlying Flask service ports in {phase}.")
    raise typer.Exit(2)


@cli.command("seed-demo")
def seed_demo() -> None:
    _phase_not_ported("seed-demo", "a later data/UX phase")


@cli.command("seed-defaults")
def seed_defaults() -> None:
    _phase_not_ported("seed-defaults", "the transaction/category phase")


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
    _phase_not_ported("sync-live-bank-data", "the Plaid integration phase")


@cli.command("run-control-evaluations")
def run_control_evaluations() -> None:
    _phase_not_ported("run-control-evaluations", "the compliance/admin phase")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
