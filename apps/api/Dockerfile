# Production image for the ClearPath FastAPI API.
#
# Built for Railway (set the service Root Directory to `apps/api`), but this is a
# plain container so it also runs on Render, Fly, ECS, or a VPS unchanged.
#
# Migrations are intentionally NOT run here. Run `alembic upgrade head` as a
# Railway pre-deploy command (or an explicit release step) so concurrent
# replicas can never race each other applying migrations. See cutover-runbook.md.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Pinned to the same uv version CI uses, so local, CI, and prod resolve identically.
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer first (cached until pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application layer.
COPY . .
RUN uv sync --frozen --no-dev

# Put the venv (and the `clearpath` console script) on PATH so `clearpath
# seed-defaults` / `run-control-evaluations` work inside the container.
ENV PATH="/app/.venv/bin:$PATH"

# Drop privileges.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Railway (and most PaaS) inject $PORT; fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
