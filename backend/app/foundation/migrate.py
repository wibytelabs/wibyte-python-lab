"""Explicit dedicated-owner migrations with transaction-scoped advisory lock."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from backend.app.foundation.settings import postgres_url

MIGRATION_LOCK = 78241720501
class FoundationMigrationError(RuntimeError):
    pass

def migrate(database_url: str, revision: str = "head", *, downgrade: bool = False):
    url = postgres_url(database_url, "WPL_MIGRATION_DATABASE_URL")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True, connect_args={
        "connect_timeout": 5, "application_name": "wpl-foundation-migration",
        "options": "-c statement_timeout=60000 -c lock_timeout=10000 -c idle_in_transaction_session_timeout=30000"})
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
            allowed = connection.execute(text("""
                SELECT n.nspowner=r.oid AND NOT r.rolsuper AND NOT r.rolbypassrls
                FROM pg_namespace n CROSS JOIN pg_roles r
                WHERE n.nspname='wpl' AND r.rolname=current_user
            """)).scalar_one_or_none()
            if allowed is not True:
                raise FoundationMigrationError("Migration requires the dedicated wpl schema owner.")
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic_foundation.ini"))
            config.attributes["connection"] = connection
            (command.downgrade if downgrade else command.upgrade)(config, revision)
    except FoundationMigrationError:
        raise
    except Exception:
        raise FoundationMigrationError("Foundation migration failed; database details redacted.") from None
    finally:
        engine.dispose()
