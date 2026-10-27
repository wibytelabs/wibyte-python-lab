"""Actual runtime primary/recovery preview policy; owner connections seed only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import threading
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.organizations.transfers import preview_transfer
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.migrate import migrate
from backend.app.foundation.settings import FoundationSettings,postgres_url
from test_schema import connect,seed_org
from test_guards import add_member


class TransferPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture preview target.')
        cls.database=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=url,pool_size=2))
        cls.addClassCleanup(cls.database.close)

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.admin,self.member=add_member(owner,self.a['org'])
            self.student,self.student_member=add_member(owner,self.a['org'],('student',))
            self.executive,self.other=uuid4(),uuid4()
            for actor in (self.executive,self.other):
                owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(actor,))
                owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Synthetic directory grant')",(actor,))
            for fixture in (self.a,self.b):owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))

    def context(self,actor=None,scope=RequestScope.TENANT,org=None):
        return RequestContext(VerifiedIdentity(actor or self.a['user']),scope,org or self.a['org'])

    def version(self):
        with connect() as owner:return owner.execute('SELECT version FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone()[0]

    def preview(self,context=None,target=None,version=None,reason='Synthetic primary transfer reason'):
        with self.database.request_transaction(context or self.context()) as session:
            return preview_transfer(session,context or self.context(),target or self.member,
                self.version() if version is None else version,reason)

    def recover(self):
        with connect() as owner:
            owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
            for actor in (self.executive,self.other):
                owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'recovery','Synthetic recovery grant')",(actor,))
        return self.context(self.executive,RequestScope.PLATFORM)

    def count(self):
        with connect() as owner:return owner.execute('SELECT count(*) FROM wpl.primary_admin_transfers WHERE org_id=%s',(self.a['org'],)).fetchone()[0]

    def test_primary_preview_stores_only_digest_and_audit_without_changing_designation(self):
        version=self.version();preview=self.preview(version=version)
        self.assertEqual((preview.org_id,preview.from_membership_id,preview.to_membership_id,preview.authorization_scope),
            (self.a['org'],self.a['member'],self.member,'tenant'))
        self.assertNotIn(preview.confirmation,repr(preview))
        with connect() as owner:
            row=owner.execute('SELECT confirmation_hash,status,reason,authorization_scope,expires_at>now(),expires_at<=now()+interval \'5 minutes\' FROM wpl.primary_admin_transfers WHERE id=%s',(preview.transfer_id,)).fetchone()
            self.assertEqual(bytes(row[0]),hashlib.sha256(preview.confirmation.encode()).digest())
            self.assertEqual(row[1:],('preview','Synthetic primary transfer reason','tenant',True,True))
            self.assertEqual(owner.execute('SELECT primary_admin_membership_id,version FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone(),(self.a['member'],version))
            audit=owner.execute("SELECT actor_id,changes FROM wpl.audit_events WHERE target_id=%s AND action='primary_transfer_previewed'",(preview.transfer_id,)).fetchone()
            self.assertEqual(audit[0],self.a['user']);self.assertNotIn(preview.confirmation,str(audit))
            self.assertNotIn('confirmation_hash',str(audit))
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.jobs WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_target_eligibility_and_expected_version_fail_without_preview_or_business_change(self):
        for target in (self.a['member'],self.b['member'],self.student_member,uuid4()):
            with self.subTest(target=str(target)),self.assertRaises(TenantConflict) as error:self.preview(target=target)
            self.assertEqual(error.exception.code,'target_ineligible')
        for column,value in (('status','suspended'),('status','removed')):
            with connect() as owner:owner.execute('UPDATE wpl.organization_memberships SET status=%s WHERE id=%s',(value,self.member))
            with self.assertRaises(TenantConflict) as error:self.preview()
            self.assertEqual(error.exception.code,'target_ineligible')
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.member,))
        with self.assertRaises(TenantConflict) as error:self.preview(version=self.version()+1)
        self.assertEqual(error.exception.code,'version_conflict')
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.admin,))
        with self.assertRaises(TenantConflict) as error:self.preview()
        self.assertEqual(error.exception.code,'target_ineligible');self.assertEqual(self.count(),0)

    def test_only_current_primary_can_preview_ordinary_transfer(self):
        for actor in (self.admin,self.student,self.executive,self.b['user']):
            with self.subTest(actor=str(actor)),self.assertRaises(AuthorizationDenied):self.preview(self.context(actor))
        with self.assertRaises(AuthorizationDenied):self.preview(self.context(self.executive,RequestScope.PLATFORM))
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
        with self.assertRaises(AuthorizationDenied):self.preview()
        self.assertEqual(self.count(),0)

    def test_recovery_requires_separate_current_capability_target_and_recovery_state(self):
        with connect() as owner:owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'recovery','Synthetic grant')",(self.executive,))
        context=self.context(self.executive,RequestScope.PLATFORM)
        with self.assertRaises(AuthorizationDenied):self.preview(context)
        context=self.recover_without_duplicate_grant()
        with self.assertRaises(AuthorizationDenied):self.preview(self.context(self.executive,RequestScope.PLATFORM,self.b['org']))
        preview=self.preview(context);self.assertEqual(preview.authorization_scope,'platform')
        with connect() as owner:owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s AND capability='recovery'",(self.executive,))
        with self.assertRaises(AuthorizationDenied):self.preview(context)
        with connect() as owner:
            owner.execute("UPDATE wpl.platform_roles SET expires_at=NULL WHERE user_id=%s AND capability='recovery'",(self.executive,))
            owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.executive,))
        with self.assertRaises(AuthorizationDenied):self.preview(context)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status,primary_admin_membership_id FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone(),('recovery_required',self.a['member']))

    def recover_without_duplicate_grant(self):
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
        return self.context(self.executive,RequestScope.PLATFORM)

    def test_replacement_expiry_and_other_actor_cannot_overwrite_live_preview(self):
        context=self.recover();first=self.preview(context);second=self.preview(context)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.primary_admin_transfers WHERE id=%s',(first.transfer_id,)).fetchone()[0],'cancelled')
        other=self.context(self.other,RequestScope.PLATFORM)
        with self.assertRaises(TenantConflict) as error:self.preview(other)
        self.assertEqual(error.exception.code,'preview_in_progress')
        with connect() as owner:owner.execute("UPDATE wpl.primary_admin_transfers SET expires_at=now()-interval '1 second' WHERE id=%s",(second.transfer_id,))
        third=self.preview(other)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.primary_admin_transfers WHERE id=%s',(second.transfer_id,)).fetchone()[0],'expired')
            self.assertEqual(owner.execute("SELECT id FROM wpl.primary_admin_transfers WHERE org_id=%s AND status='preview'",(self.a['org'],)).fetchall(),[(third.transfer_id,)])

    def test_competing_recovery_actors_serialize_to_one_live_preview(self):
        self.recover();version=self.version();barrier=threading.Barrier(2)
        def run(actor):
            context=self.context(actor,RequestScope.PLATFORM)
            with self.database.request_transaction(context) as session:
                barrier.wait(timeout=5)
                try:preview_transfer(session,context,self.member,version,'Synthetic competing recovery reason');return 'created'
                except TenantConflict as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,actor) for actor in (self.executive,self.other)]
            result=[future.result(timeout=15) for future in futures]
        self.assertCountEqual(result,['created','preview_in_progress']);self.assertEqual(self.count(),1)
        print('Actual wpl_app recovery previews: one live actor-bound preview; competing actor conflicts; designation unchanged.',flush=True)

    def test_outer_rollback_and_caught_audit_error_restore_prior_preview(self):
        context=self.context();version=self.version()
        with self.assertRaisesRegex(RuntimeError,'Synthetic outer failure'):
            with self.database.request_transaction(context) as session:
                preview_transfer(session,context,self.member,version,'Synthetic rollback reason')
                raise RuntimeError('Synthetic outer failure')
        self.assertEqual(self.count(),0)
        prior=self.preview()
        with connect() as owner:owner.execute("ALTER TABLE wpl.audit_events ADD CONSTRAINT fixture_reject_transfer_preview CHECK(action<>'primary_transfer_previewed') NOT VALID")
        try:
            with self.database.request_transaction(context) as session:
                with self.assertRaises(DBAPIError) as error:preview_transfer(session,context,self.member,version,'Synthetic failing audit')
                self.assertEqual(error.exception.orig.sqlstate,'23514')
                self.assertEqual(session.execute(text('SELECT 1')).scalar_one(),1)
        finally:
            with connect() as owner:owner.execute('ALTER TABLE wpl.audit_events DROP CONSTRAINT fixture_reject_transfer_preview')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT id,status FROM wpl.primary_admin_transfers WHERE org_id=%s',(self.a['org'],)).fetchall(),[(prior.transfer_id,'preview')])
        self.assertEqual(self.version(),version)

    def test_context_invalid_input_and_raw_privileges_fail_closed(self):
        context=self.context();version=self.version()
        with self.database.request_transaction(self.context(self.admin)) as session:
            with self.assertRaises(AuthorizationDenied):preview_transfer(session,context,self.member,version,'Synthetic substituted actor')
        for version_value,reason in ((True,'Synthetic reason'),(version,'bad'),(version,'Reason\nwith newline')):
            with self.assertRaises(TenantConflict):self.preview(version=version_value,reason=reason)
        with self.database.request_transaction(context) as session:
            value=session.execute(text("SELECT wpl.preview_primary_transfer(:org,:target,:version,'Valid reason',:id,:hash)"),
                {'org':self.a['org'],'target':self.member,'version':version,'id':uuid4(),'hash':b'x'}).scalar_one()
            self.assertEqual(value,{'error':'invalid_preview'})
        for statement in ('SELECT * FROM wpl.primary_admin_transfers','SELECT wpl.primary_transfer_allowed(:org)',
                          "UPDATE wpl.organizations SET primary_admin_membership_id=:target WHERE id=:org"):
            with self.assertRaises(DBAPIError) as error:
                with self.database.request_transaction(context) as session:session.execute(text(statement),{'org':self.a['org'],'target':self.member})
            self.assertEqual(error.exception.orig.sqlstate,'42501')
        with connect('WORKER') as worker:
            with self.assertRaises(Exception) as error:worker.execute('SELECT wpl.preview_primary_transfer(%s,%s,%s,%s,%s,%s)',
                (self.a['org'],self.member,version,'Synthetic denied worker',uuid4(),b'x'*32))
            self.assertEqual(error.exception.sqlstate,'42501')
        self.assertEqual(self.count(),0)
