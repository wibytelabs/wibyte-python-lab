"""Private personal legacy archive for confirmed owned-fixture rehearsal only."""
from pathlib import Path
from alembic import op
revision='p0219_import_rehearsal'
down_revision='p0218_transfer_job_read'
branch_labels=None
depends_on=None


def upgrade():
    for statement in Path(__file__).with_suffix('.sql').read_text().split('-- statement --'):
        op.execute(statement.strip())
    for name in ('legacy_import_runs','legacy_import_artifacts'):
        op.execute(f'ALTER TABLE wpl.{name} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE wpl.{name} FROM PUBLIC,wpl_app,wpl_worker')
        op.execute(f'CREATE TRIGGER archive_append_only BEFORE UPDATE OR DELETE ON wpl.{name} '
            'FOR EACH ROW EXECUTE FUNCTION wpl.reject_audit_mutation()')


def downgrade():
    op.execute('DROP TABLE wpl.legacy_import_artifacts')
    op.execute('DROP TABLE wpl.legacy_import_runs')
