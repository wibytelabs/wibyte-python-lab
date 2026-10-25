"""Private schema permissions. Tenant tables follow in P02.2."""
from alembic import op
revision = "p0201_private_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("REVOKE ALL ON SCHEMA wpl FROM PUBLIC")
    op.execute("REVOKE ALL ON TABLE wpl.alembic_version FROM PUBLIC, wpl_app, wpl_worker")

def downgrade():
    # Never drop externally provisioned roles/schema as a migration side effect.
    pass
