from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.models import Base  # noqa: E402


def run_migrations() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    if not database_url.startswith("postgresql+psycopg://") and not database_url.startswith("sqlite:///"):
        raise RuntimeError("Expected PostgreSQL psycopg URL; SQLite is allowed only for isolated migration tests")
    if database_url.startswith("sqlite:///") and os.environ.get("APP_MODE") != "dev":
        raise RuntimeError("SQLite migrations allowed only in dev test mode")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata,
                          compare_type=True, transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
