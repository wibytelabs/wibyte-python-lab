"""Actual app role confirmation/recovery, locks, rollback and notification intent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import hashlib
import threading
import time
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import AuthorizationDenied,TenantConflict
from backend.app.domains.organizations.transfers import preview_transfer,confirm_transfer
from backend.app.domains.organizations.service import set_member_status
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings
from test_schema import connect
import test_transfer_preview as preview_fixtures


class TransferCompletionTests(unittest.TestCase):
    setUpClass=classmethod(preview_fixtures.TransferPreviewTests.setUpClass.__func__)
    setUp=preview_fixtures.TransferPreviewTests.setUp
    version=preview_fixtures.TransferPreviewTests.version
    recover=preview_fixtures.TransferPreviewTests.recover

    def context(self,actor=None,scope=RequestScope.TENANT,org=None,*,authenticated=True):
        return RequestContext(VerifiedIdentity(actor or self.a['user'],
            datetime.now(timezone.utc) if authenticated else None),scope,org or self.a['org'])

    def preview(self,context=None):
        context=context or self.context()
        with self.database.request_transaction(context) as session:
            return preview_transfer(session,context,self.member,self.version(),'Synthetic protected primary change reason')

    def confirm(self,preview,context=None,*,confirmation=None,version=None):
        context=context or self.context()
        with self.database.request_transaction(context) as session:
            return confirm_transfer(session,context,preview.transfer_id,
                preview.expected_version if version is None else version,
                preview.confirmation if confirmation is None else confirmation)

    def state(self):
        with connect() as owner:
            org=owner.execute('SELECT primary_admin_membership_id,status,version,access_epoch FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone()
            jobs=owner.execute("SELECT id,kind,state,delivery_status,private_payload_id,intent_hash FROM wpl.jobs WHERE org_id=%s",(self.a['org'],)).fetchall()
            return org,jobs

    def test_atomic_transfer_retains_old_admin_and_queues_only_redacted_notification_intent(self):
        preview=self.preview();before=self.state()[0];outcome=self.confirm(preview)
        self.assertFalse(outcome.replayed);body=outcome.public
        self.assertEqual((body['primary_admin_membership_id'],body['version'],body['access_epoch']),
            (str(self.member),before[2]+1,before[3]+1))
        self.assertEqual(body['delivery_status'],'pending_integration')
        org,jobs=self.state();self.assertEqual(org[:2],(self.member,'active'));self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0][1:5],('notify_primary_transfer','queued','pending_integration',None))
        self.assertEqual(len(jobs[0][5]),64)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.a['member'],)).fetchone()[0],'active')
            self.assertEqual(owner.execute("SELECT role FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s",(self.a['org'],self.a['member'])).fetchall(),[('admin',)])
            self.assertEqual(owner.execute('SELECT state,event_kind FROM wpl.outbox WHERE job_id=%s',(jobs[0][0],)).fetchall(),[('pending','primary_transfer_notification_requested')])
            row=owner.execute('SELECT status,result FROM wpl.primary_admin_transfers WHERE id=%s',(preview.transfer_id,)).fetchone()
            self.assertEqual(row,('completed',body))
            audit=owner.execute("SELECT actor_id,reason,changes FROM wpl.audit_events WHERE org_id=%s AND action='primary_transferred'",(self.a['org'],)).fetchone()
            self.assertEqual(audit[:2],(self.a['user'],'Synthetic protected primary change reason'))
            for secret in (preview.confirmation,'confirmation_hash','contact@example.invalid'):
                self.assertNotIn(secret,str((audit,body,jobs)))
        print('Actual wpl_app primary change: one designation/version/epoch, former admin retained, audited pending notification job/outbox; no provider called.',flush=True)

    def test_explicit_recovery_uses_current_separate_capability_without_unblocking_old_identity(self):
        context=self.recover();preview=self.preview(context);before=self.state()[0]
        with connect() as owner:owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s AND capability='recovery'",(self.executive,))
        with self.assertRaises(AuthorizationDenied):self.confirm(preview,context)
        self.assertEqual(self.state()[1],[])
        with connect() as owner:owner.execute("UPDATE wpl.platform_roles SET expires_at=NULL WHERE user_id=%s AND capability='recovery'",(self.executive,))
        result=self.confirm(preview,context).public
        self.assertEqual((result['status'],result['primary_admin_membership_id']),('active',str(self.member)))
        self.assertEqual((result['version'],result['access_epoch']),(before[2]+1,before[3]+1))
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT global_state FROM wpl.users WHERE id=%s',(self.a['user'],)).fetchone()[0],'suspended')
            self.assertEqual(owner.execute('SELECT status FROM wpl.organization_memberships WHERE id=%s',(self.a['member'],)).fetchone()[0],'active')
            self.assertEqual(owner.execute("SELECT actor_id,reason FROM wpl.audit_events WHERE org_id=%s AND action='primary_recovered'",(self.a['org'],)).fetchall(),[(self.executive,'Synthetic protected primary change reason')])
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.platform_roles WHERE user_id=%s',(self.admin,)).fetchone()[0],0)
        with self.assertRaises(AuthorizationDenied):self.confirm(preview,self.context())
        with connect() as owner:owner.execute("DELETE FROM wpl.platform_roles WHERE user_id=%s AND capability='recovery'",(self.executive,))
        with self.assertRaises(AuthorizationDenied):self.confirm(preview,context)
        self.assertEqual(len(self.state()[1]),1)

    def test_recent_auth_confirmation_expiry_version_and_actor_scope_are_required(self):
        preview=self.preview()
        cases=[(self.context(authenticated=False),'recent_auth_required'),
            (RequestContext(VerifiedIdentity(self.a['user'],datetime.now(timezone.utc)-timedelta(minutes=6)),RequestScope.TENANT,self.a['org']),'recent_auth_required'),
            (RequestContext(VerifiedIdentity(self.a['user'],datetime.now(timezone.utc)+timedelta(minutes=1)),RequestScope.TENANT,self.a['org']),'recent_auth_required')]
        for context,code in cases:
            with self.assertRaises(TenantConflict) as error:self.confirm(preview,context)
            self.assertEqual(error.exception.code,code)
        for phrase,version in (('wrong-confirmation',preview.expected_version),(preview.confirmation,preview.expected_version+1)):
            with self.assertRaises(TenantConflict) as error:self.confirm(preview,confirmation=phrase,version=version)
            self.assertEqual(error.exception.code,'invalid_confirmation')
        with self.assertRaises(TenantConflict):self.confirm(preview,self.context(self.admin))
        with self.assertRaises(AuthorizationDenied):self.confirm(preview,self.context(self.executive,RequestScope.PLATFORM))
        with connect() as owner:owner.execute("UPDATE wpl.primary_admin_transfers SET expires_at=now()-interval '1 second' WHERE id=%s",(preview.transfer_id,))
        with self.assertRaises(TenantConflict) as error:self.confirm(preview)
        self.assertEqual(error.exception.code,'invalid_confirmation');self.assertEqual(self.state()[1],[])

    def test_version_target_role_removal_and_superseded_preview_cannot_mutate(self):
        preview=self.preview()
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='removed' WHERE id=%s",(self.member,))
        with self.assertRaises(TenantConflict) as error:self.confirm(preview)
        self.assertEqual(error.exception.code,'version_conflict')
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.member,))
        newer=self.preview();latest=self.preview()
        with self.assertRaises(TenantConflict) as error:self.confirm(newer)
        self.assertEqual(error.exception.code,'invalid_confirmation')
        with connect() as owner:owner.execute("DELETE FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s AND role='admin'",(self.a['org'],self.member))
        with self.assertRaises(TenantConflict) as error:self.confirm(latest)
        self.assertEqual(error.exception.code,'version_conflict')
        self.assertEqual(self.state()[1],[])

    def test_same_preview_concurrent_confirmations_commit_one_change_and_replay_same_receipt(self):
        preview=self.preview();barrier=threading.Barrier(2)
        def run():
            context=self.context()
            with self.database.request_transaction(context) as session:
                barrier.wait(timeout=5)
                return confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run) for _ in range(2)]
            results=[future.result(timeout=15) for future in futures]
        self.assertEqual(results[0].public,results[1].public)
        self.assertCountEqual([result.replayed for result in results],[False,True])
        self.assertEqual(len(self.state()[1]),1)
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='primary_transferred'",(self.a['org'],)).fetchone()[0],1)
        print('Actual competing wpl_app confirmations: one designation change/notification intent; identical committed receipt replayed.',flush=True)

    def test_target_removal_race_leaves_one_valid_primary_and_no_partial_intent(self):
        preview=self.preview();barrier=threading.Barrier(2)
        with connect() as owner:member_version=owner.execute('SELECT version FROM wpl.organization_memberships WHERE id=%s',(self.member,)).fetchone()[0]
        def transfer():
            context=self.context()
            with self.database.request_transaction(context) as session:
                barrier.wait(timeout=5)
                try:confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation);return 'transferred'
                except TenantConflict as error:return error.code
        def remove():
            context=self.context()
            with self.database.request_transaction(context) as session:
                barrier.wait(timeout=5)
                try:set_member_status(session,context.identity,self.a['org'],self.member,'removed',member_version,'Synthetic competing removal');return 'removed'
                except TenantConflict as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(transfer),pool.submit(remove)]
            results=[future.result(timeout=15) for future in futures]
        self.assertTrue(results in (['transferred','protected_primary'],['version_conflict','removed']),results)
        org,jobs=self.state();self.assertEqual(len(jobs),int(results[0]=='transferred'))
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT m.status,u.global_state,r.role FROM wpl.organization_memberships m JOIN wpl.users u ON u.id=m.user_id JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id WHERE m.org_id=%s AND m.id=%s AND r.role='admin'",(self.a['org'],org[0])).fetchone(),('active','active','admin'))
        print('Actual runtime transfer/removal race:',results,flush=True)

    def test_audit_or_outbox_constraint_failure_rolls_back_designation_receipt_and_queue(self):
        preview=self.preview();before=self.state()[0];context=self.context()
        for table,name,condition in (
            ('audit_events','fixture_reject_primary_change',"action<>'primary_transferred'"),
            ('outbox','fixture_reject_primary_notice',"event_kind<>'primary_transfer_notification_requested'")):
            with connect() as owner:owner.execute(f'ALTER TABLE wpl.{table} ADD CONSTRAINT {name} CHECK({condition}) NOT VALID')
            try:
                with self.database.request_transaction(context) as session:
                    with self.assertRaises(DBAPIError) as error:confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation)
                    self.assertEqual(error.exception.orig.sqlstate,'23514')
                    self.assertEqual(session.execute(text('SELECT 1')).scalar_one(),1)
            finally:
                with connect() as owner:owner.execute(f'ALTER TABLE wpl.{table} DROP CONSTRAINT {name}')
            self.assertEqual(self.state(),(before,[]))
            with connect() as owner:self.assertEqual(owner.execute('SELECT status,result FROM wpl.primary_admin_transfers WHERE id=%s',(preview.transfer_id,)).fetchone(),('preview',None))

    def test_outer_rollback_retry_and_new_pool_replay_recheck_current_permission(self):
        preview=self.preview();context=self.context();before=self.state()[0]
        with self.assertRaisesRegex(RuntimeError,'Synthetic outer rollback'):
            with self.database.request_transaction(context) as session:
                confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation)
                raise RuntimeError('Synthetic outer rollback')
        self.assertEqual(self.state(),(before,[]))
        first=self.confirm(preview)
        fresh=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=self.database.engine.url,pool_size=1));self.addCleanup(fresh.close)
        with fresh.request_transaction(context) as session:replayed=confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation)
        self.assertTrue(replayed.replayed);self.assertEqual(first.public,replayed.public)
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='removed' WHERE id=%s",(self.a['member'],))
        with self.assertRaises(AuthorizationDenied):self.confirm(preview)
        self.assertEqual(len(self.state()[1]),1)

    def test_target_global_suspension_is_serialized_before_designation_and_has_no_effect(self):
        preview=self.preview();context=self.context()
        owner=connect();self.addCleanup(owner.close)
        owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.admin,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.confirm,preview,context)
            try:
                deadline=time.monotonic()+5;waiting=False
                while time.monotonic()<deadline:
                    rows=owner.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity a WHERE a.application_name='wpl-foundation' AND a.usename='wpl_app' AND pg_backend_pid()=ANY(pg_blocking_pids(a.pid)))").fetchone()
                    if rows[0]:waiting=True;break
                    if future.done():break
                    time.sleep(0.01)
                self.assertTrue(waiting,'Confirmation must wait on the actual target identity lock.')
            finally:owner.commit()
            with self.assertRaises(TenantConflict) as error:future.result(timeout=15)
            self.assertEqual(error.exception.code,'target_ineligible')
        self.assertEqual(self.state()[1],[])
        self.assertEqual(self.state()[0][0],self.a['member'])
        print('Actual target-global suspension: confirmation waited for user lock, rechecked blocked target and created no designation/job change.',flush=True)

    def test_context_raw_auth_and_direct_privileges_cannot_bypass_confirmation(self):
        preview=self.preview();context=self.context()
        with self.database.request_transaction(self.context(self.admin)) as session:
            with self.assertRaises(AuthorizationDenied):confirm_transfer(session,context,preview.transfer_id,preview.expected_version,preview.confirmation)
        for auth in ('malformed','999999999999','-1',''):
            with self.database.request_transaction(context) as session:
                session.execute(text("SELECT set_config('wpl.auth_time',:value,true)"),{'value':auth})
                result=session.execute(text('SELECT wpl.confirm_primary_transfer(:org,:id,:version,:hash,:job)'),
                    {'org':self.a['org'],'id':preview.transfer_id,'version':preview.expected_version,
                     'hash':hashlib.sha256(preview.confirmation.encode()).digest(),'job':uuid4()}).scalar_one()
                self.assertEqual(result,{'error':'recent_auth_required'})
        for statement in ('SELECT wpl.primary_transfer_receipt_allowed(:org)',
            "UPDATE wpl.organizations SET primary_admin_membership_id=:target WHERE id=:org",
            'SELECT result FROM wpl.primary_admin_transfers'):
            with self.assertRaises(DBAPIError) as error:
                with self.database.request_transaction(context) as session:session.execute(text(statement),{'org':self.a['org'],'target':self.member})
            self.assertEqual(error.exception.orig.sqlstate,'42501')
        with connect('WORKER') as worker:
            with self.assertRaises(Exception) as error:worker.execute('SELECT wpl.confirm_primary_transfer(%s,%s,%s,%s,%s)',
                (self.a['org'],preview.transfer_id,preview.expected_version,b'x'*32,uuid4()))
            self.assertEqual(error.exception.sqlstate,'42501')
        self.assertEqual(self.state()[1],[])
