"""Real restricted-worker payload/fencing/retry proof without delivery adapters."""
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.jobs.transitions import load_delivery,authorize_delivery,finish_delivery
from test_schema import connect
from test_guards import add_member
from test_enqueue import invitation
import test_worker_leases as lease_fixtures


class WorkerTransitionTests(unittest.TestCase):
    # Reuse fixture utilities, not the lease test cases themselves.
    setUpClass=classmethod(lease_fixtures.WorkerLeaseTests.setUpClass.__func__)
    tearDownClass=classmethod(lease_fixtures.WorkerLeaseTests.tearDownClass.__func__)
    setUp=lease_fixtures.WorkerLeaseTests.setUp
    clear_jobs=lease_fixtures.WorkerLeaseTests.clear_jobs
    enqueue=lease_fixtures.WorkerLeaseTests.enqueue
    claim=lease_fixtures.WorkerLeaseTests.claim
    expire=lease_fixtures.WorkerLeaseTests.expire

    def get_payload(self,lease):
        material=load_delivery(self.worker,self.worker_id,lease)
        self.assertIsNotNone(material)
        self.assertEqual(self.worker.engine.pool.checkedout(),0)
        return material,self.cipher.decrypt(material.envelope,material.binding)

    def test_payload_is_fenced_bound_redacted_and_decrypted_outside_database_transaction(self):
        identifier=self.enqueue()
        lease=self.claim(batch_size=1)[0]
        material,payload=self.get_payload(lease)
        self.assertEqual(material.binding.operation_id,identifier)
        self.assertEqual(material.binding.actor_id,lease.actor_id)
        self.assertEqual(material.binding.scope_id,lease.org_id)
        self.assertNotIn(payload['activation_token'],repr(material))
        self.assertNotIn(payload['email'],repr(material))
        self.assertTrue(authorize_delivery(self.worker,self.worker_id,lease,payload))
        self.assertEqual(self.worker.engine.pool.checkedout(),0)
        self.assertIsNone(load_delivery(self.worker,uuid4(),lease))
        self.assertFalse(authorize_delivery(self.worker,uuid4(),lease,payload))
        self.expire(identifier)
        self.assertIsNone(load_delivery(self.worker,self.worker_id,lease))
        self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,payload))

    def test_late_completion_after_expiry_reclaim_cannot_override_new_generation(self):
        identifier=self.enqueue()
        old=self.claim(batch_size=1)[0]
        self.expire(identifier)
        self.assertIsNone(finish_delivery(self.worker,self.worker_id,old,outcome='success'))
        new_owner=uuid4();new=self.claim(new_owner,batch_size=1)[0]
        self.assertEqual(new.lease_generation,old.lease_generation+1)
        self.assertIsNone(finish_delivery(self.worker,self.worker_id,old,outcome='success'))
        self.assertIsNone(finish_delivery(self.worker,self.worker_id,new,outcome='success'))
        self.assertEqual(finish_delivery(self.worker,new_owner,new,outcome='success'),'succeeded')
        self.assertIsNone(finish_delivery(self.worker,new_owner,new,outcome='success'))
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,lease_owner,lease_until FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('succeeded',None,None))
            rows=owner.execute("SELECT actor_id,changes FROM wpl.audit_events WHERE target_id=%s AND action='job_succeeded'",(identifier,)).fetchall()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0][0],new.actor_id)
            self.assertEqual(rows[0][1]['worker_id'],str(new_owner))
            self.assertEqual(rows[0][1]['lease_generation'],new.lease_generation)
        print('Actual wpl_worker completion: expired/foreign/stale generations rejected; current generation committed once. No external delivery claimed.',flush=True)

    def test_retry_backoff_is_persisted_and_attempt_limit_dead_letters(self):
        identifier=self.enqueue()
        for attempt in range(1,6):
            lease=self.claim(batch_size=1)[0]
            self.assertEqual(lease.attempts,attempt)
            state=finish_delivery(self.worker,self.worker_id,lease,outcome='retry',error_code='transport_unavailable')
            self.assertEqual(state,'dead' if attempt==5 else 'queued')
            with connect() as owner:
                row=owner.execute('SELECT state,attempts,available_at,updated_at,last_error_code,lease_owner,lease_until FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone()
                self.assertEqual(row[:2],(state,attempt))
                self.assertEqual(row[4:],('transport_unavailable',None,None))
                if attempt<5:
                    self.assertEqual((row[2]-row[3]).total_seconds(),5*(2**(attempt-1)))
                    owner.execute("UPDATE wpl.jobs SET available_at='1990-01-01' WHERE id=%s",(identifier,))
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_retry_scheduled'",(identifier,)).fetchone()[0],4)
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_dead'",(identifier,)).fetchone()[0],1)

    def test_actor_global_member_role_and_org_revocation_block_effect_access_and_completion(self):
        for kind in ('global','member','role','organization'):
            with self.subTest(kind=kind):
                with connect() as owner:actor,member=add_member(owner,self.a['org'],('admin',))
                identifier=self.enqueue(actor=actor)
                lease=self.claim(batch_size=1)[0]
                material,payload=self.get_payload(lease)
                with connect() as owner:
                    if kind=='global':owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(actor,))
                    elif kind=='member':owner.execute("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(member,))
                    elif kind=='role':owner.execute("DELETE FROM wpl.organization_roles WHERE membership_id=%s AND role='admin'",(member,))
                    else:owner.execute("UPDATE wpl.organizations SET status='suspended' WHERE id=%s",(self.a['org'],))
                self.assertIsNone(load_delivery(self.worker,self.worker_id,lease))
                self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,payload))
                self.assertEqual(finish_delivery(self.worker,self.worker_id,lease,outcome='success'),'cancelled')
                with connect() as owner:
                    self.assertEqual(owner.execute('SELECT state,last_error_code FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('cancelled','actor_not_authorized'))

    def test_target_recheck_rejects_swapped_valid_payload_expiry_revocation_and_bad_token(self):
        identifier=self.enqueue()
        lease=self.claim(batch_size=1)[0]
        material,payload=self.get_payload(lease)
        with connect() as owner:other=invitation(owner,self.a['org'])
        self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,other))
        self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,{**payload,'activation_token':'x'*64}))
        with connect() as owner:
            owner.execute("UPDATE wpl.invitations SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=%s",(payload['invitation_id'],))
        self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,payload))
        with connect() as owner:
            owner.execute("UPDATE wpl.invitations SET expires_at=now()+interval '1 day',status='revoked' WHERE id=%s",(payload['invitation_id'],))
        self.assertFalse(authorize_delivery(self.worker,self.worker_id,lease,payload))
        self.assertEqual(finish_delivery(self.worker,self.worker_id,lease,outcome='cancel',error_code='target_unavailable'),'cancelled')

    def test_transition_rollback_restores_lease_and_does_not_append_completion(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        with self.assertRaisesRegex(RuntimeError,'synthetic transition rollback'):
            with self.worker.transaction() as session:
                self.assertEqual(session.execute(text("SELECT wpl.finish_delivery(:job,:worker,:generation,'success',NULL)"),
                    {'job':identifier,'worker':self.worker_id,'generation':lease.lease_generation}).scalar_one(),'succeeded')
                raise RuntimeError('synthetic transition rollback')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,lease_owner FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('running',self.worker_id))
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_succeeded'",(identifier,)).fetchone()[0],0)
        self.assertEqual(finish_delivery(self.worker,self.worker_id,lease,outcome='success'),'succeeded')

    def test_retry_delay_is_capped_independently_of_high_attempt_fixture(self):
        identifier=self.enqueue()
        with connect() as owner:owner.execute('UPDATE wpl.jobs SET max_attempts=10,attempts=8 WHERE id=%s',(identifier,))
        lease=self.claim(batch_size=1)[0]
        self.assertEqual(lease.attempts,9)
        # A non-exhausted high attempt fixture proves the cap without sleeps.
        self.assertEqual(finish_delivery(self.worker,self.worker_id,lease,outcome='retry',error_code='key_unavailable'),'queued')
        with connect() as owner:
            row=owner.execute('SELECT available_at-updated_at FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone()[0]
            self.assertEqual(row.total_seconds(),300)

    def test_unregistered_errors_and_privilege_bypass_are_denied_without_state_changes(self):
        identifier=self.enqueue();lease=self.claim(batch_size=1)[0]
        for outcome,error in (('success','secret_token'),('retry','provider_raw_detail'),('cancel',None),('arbitrary',None)):
            with self.subTest(outcome=outcome),self.assertRaises(ValueError):
                finish_delivery(self.worker,self.worker_id,lease,outcome=outcome,error_code=error)
        with self.assertRaises(DBAPIError) as result:
            with self.worker.transaction() as session:
                session.execute(text("SELECT wpl.finish_delivery(:job,:worker,1,'retry','provider_raw_detail')"),{'job':identifier,'worker':self.worker_id})
        self.assertEqual(result.exception.orig.sqlstate,'22023')
        for statement in ('SELECT * FROM wpl.secret_payloads',"UPDATE wpl.jobs SET state='succeeded'"):
            with self.assertRaises(DBAPIError):
                with self.worker.transaction() as session:session.execute(text(statement))
        for statement in ('SELECT * FROM wpl.delivery_payload(:job,:worker,1)',"SELECT wpl.finish_delivery(:job,:worker,1,'success',NULL)"):
            with self.assertRaises(DBAPIError) as result:
                with self.app.transaction() as session:session.execute(text(statement),{'job':identifier,'worker':self.worker_id})
            self.assertEqual(result.exception.orig.sqlstate,'42501')
        with connect() as owner:self.assertEqual(owner.execute('SELECT state FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone()[0],'running')
