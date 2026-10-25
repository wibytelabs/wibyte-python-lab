"""Allow only a verified actor's new pending identity mirror, without approval."""
from alembic import op
revision='p0205_identity_mirror'
down_revision='p0204_read_rls'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""CREATE FUNCTION wpl.identity_insert_allowed(subject uuid,state varchar,epoch bigint,row_version integer)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,wpl AS $$
        SELECT wpl.ctx_scope()='global' AND subject=wpl.ctx_uuid('wpl.actor_id')
            AND state='pending' AND epoch=1 AND row_version=1
        $$""")
    op.execute('REVOKE ALL ON FUNCTION wpl.identity_insert_allowed(uuid,character varying,bigint,integer) FROM PUBLIC,wpl_app,wpl_worker')
    op.execute('GRANT EXECUTE ON FUNCTION wpl.identity_insert_allowed(uuid,character varying,bigint,integer) TO wpl_app')
    op.execute("""CREATE POLICY own_pending_identity ON wpl.users FOR INSERT TO wpl_app
        WITH CHECK (wpl.identity_insert_allowed(id,global_state,access_epoch,version))""")
    op.execute('GRANT INSERT (id) ON wpl.users TO wpl_app')
    op.execute('CREATE INDEX memberships_org_page ON wpl.organization_memberships(org_id,created_at,id)')
    op.execute('CREATE INDEX cohorts_org_page ON wpl.cohorts(org_id,created_at,id)')


def downgrade():
    op.execute('DROP INDEX wpl.cohorts_org_page')
    op.execute('DROP INDEX wpl.memberships_org_page')
    op.execute('REVOKE INSERT (id) ON wpl.users FROM wpl_app')
    op.execute('DROP POLICY own_pending_identity ON wpl.users')
    op.execute('DROP FUNCTION wpl.identity_insert_allowed(uuid,character varying,bigint,integer)')
