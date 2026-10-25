"""Require the explicit migration runner's already-locked connection."""
from alembic import context
connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use the explicit foundation migration runner.")
context.configure(connection=connection, target_metadata=None,
                  version_table="alembic_version", version_table_schema="wpl")
with context.begin_transaction():
    context.run_migrations()
