"""
Alembic environment script.

Two things customized from the default template:
  1. Loads DATABASE_URL from .env (via python-dotenv) instead of reading a
     hardcoded sqlalchemy.url from alembic.ini — keeps one source of truth
     for DB credentials, shared with docker-compose.yml and the app itself.
  2. Points target_metadata at our models' Base.metadata, which is what
     lets `alembic revision --autogenerate` diff the real schema in models.py
     against whatever's currently in the database.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Make `backend.models` importable when alembic is run from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.models import Base  # noqa: E402

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env at the repo root "
        "and make sure it's loaded before running alembic."
    )
# Same normalization as backend/database.py — some managed Postgres
# providers hand back a bare postgres:// scheme SQLAlchemy doesn't
# recognize, and being explicit about the psycopg2 dialect is safer than
# relying on SQLAlchemy's default driver resolution. Duplicated here
# (rather than imported) to avoid pulling in backend.database's own
# import-time DATABASE_URL check into Alembic's separate startup path.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection (not our default path)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection — our default path."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()