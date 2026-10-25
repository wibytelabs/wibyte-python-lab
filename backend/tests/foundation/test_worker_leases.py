"""Actual restricted worker claim/renew races, bounds and crash recovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import threading
import unittest
from uuid import uuid4
import psycopg
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.jobs.payloads import PayloadCipher
from backend.app.domains.jobs.enqueue import prepare_invitation,enqueue_invitation
from backend.app.domains.jobs.leases import claim_deliveries,renew_delivery
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings,postgres_url
from backend.app.foundation.migrate import migrate
from test_schema import connect,seed_org
from test_enqueue import invitation,SyntheticKeys
from test_guards import add_member


class WorkerLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        def database(kind):
            url=postgres_url(os.environ[f'WPL_{kind}_DATABASE_URL'],'fixture')
            if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture worker target.')
            return FoundationDatabase(FoundationSettings(enabled=True,application_database_url=url,pool_size=2))
        cls.app=database('APPLICATION');cls.worker=database('WORKER')
        cls.worker.verify_runtime_role()

    @classmethod
    def tearDownClass(cls):cls.app.close();cls.worker.close()

    def setUp(self):
        with connect() as owner:
            self.a,self.b=seed_org(owner),seed_org(owner)
            self.admin,self.member=add_member(owner,self.a['org'],('admin',))
            for org in (self.a,self.b):owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(org['org'],))
        self.worker_id=uuid4()
        self.ids=[]
        self.cipher=PayloadCipher(SyntheticKeys(self.app))
        self.addCleanup(self.clear_jobs)

    def clear_jobs(self):
        with connect() as owner:
            for identifier in self.ids:
                owner.execute("UPDATE wpl.jobs SET state='cancelled',lease_owner=NULL,lease_until=NULL WHERE id=%s AND state IN ('queued','running')",(identifier,))

    def enqueue(self,org=None,actor=None):
        org=org or self.a
        context=RequestContext(VerifiedIdentity(actor or org['user']),RequestScope.TENANT,org['org'])
        with connect() as owner:payload=invitation(owner,org['org'])
        identifier=uuid4()
        prepared=prepare_invitation(context,identifier,self.cipher,payload)
        with self.app.request_transaction(context) as session:enqueue_invitation(session,context,prepared)
        with connect() as owner:
            owner.execute("UPDATE wpl.jobs SET available_at='1990-01-01' WHERE id=%s",(identifier,))
        self.ids.append(identifier)
        return identifier

    def claim(self,worker=None,**options):return claim_deliveries(self.worker,worker or self.worker_id,**options)

    def expire(self,identifier):
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(identifier,))

    def test_competing_workers_claim_disjoint_jobs_across_tenants_and_commit_before_return(self):
        identifiers={self.enqueue(),self.enqueue(self.b)}
        barrier=threading.Barrier(2)
        def run():
            barrier.wait(timeout=5)
            return self.claim(uuid4(),batch_size=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run) for _ in range(2)]
            leases=[future.result(timeout=15)[0] for future in futures]
        self.assertEqual({lease.job_id for lease in leases},identifiers)
        self.assertTrue(all(lease.attempts==1 and lease.lease_generation==1 for lease in leases))
        self.assertEqual(self.worker.engine.pool.checkedout(),0)
        with connect() as owner:
            for lease in leases:
                self.assertEqual(owner.execute('SELECT state,lease_generation FROM wpl.jobs WHERE id=%s',(lease.job_id,)).fetchone(),('running',1))
                self.assertEqual(owner.execute('SELECT state FROM wpl.outbox WHERE job_id=%s',(lease.job_id,)).fetchone()[0],'dispatched')
                event=owner.execute("SELECT actor_id,changes FROM wpl.audit_events WHERE target_id=%s AND action='job_claimed'",(lease.job_id,)).fetchone()
                self.assertEqual(event[0],lease.actor_id)
                self.assertEqual(event[1]['lease_generation'],1)
                self.assertEqual(set(event[1]),{'worker_id','lease_generation','attempt','state','error_code'})
        print('Actual wpl_worker competing claims: distinct tenant jobs; committed owner/generation leases, no external effect.',flush=True)

    def test_skip_locked_does_not_wait_for_another_claim_transaction(self):
        first,second=self.enqueue(),self.enqueue()
        with connect() as owner:
            owner.execute("UPDATE wpl.jobs SET available_at='1989-01-01' WHERE id=%s",(first,))
            owner.execute('SELECT id FROM wpl.jobs WHERE id=%s FOR UPDATE',(first,))
            lease=self.claim(batch_size=1)[0]
            self.assertEqual(lease.job_id,second)

    def test_expiry_reclaim_advances_generation_and_rejects_old_or_wrong_owner_renewal(self):
        identifier=self.enqueue()
        old=self.claim(batch_size=1)[0]
        self.expire(identifier)
        self.assertFalse(renew_delivery(self.worker,self.worker_id,old))
        new_worker=uuid4();new=self.claim(new_worker,batch_size=1)[0]
        self.assertEqual(new.job_id,identifier)
        self.assertEqual((new.lease_generation,new.attempts),(2,2))
        self.assertFalse(renew_delivery(self.worker,self.worker_id,old))
        self.assertFalse(renew_delivery(self.worker,self.worker_id,new))
        self.assertFalse(renew_delivery(self.worker,new_worker,replace(new,lease_generation=1)))
        self.assertTrue(renew_delivery(self.worker,new_worker,new))

    def test_claim_rollback_leaves_job_outbox_and_audit_unchanged(self):
        identifier=self.enqueue()
        with self.assertRaisesRegex(RuntimeError,'synthetic claim crash'):
            with self.worker.transaction() as session:
                rows=session.execute(text('SELECT * FROM wpl.claim_deliveries(:worker,1,60)'),{'worker':self.worker_id}).mappings().all()
                self.assertEqual(rows[0]['job_id'],identifier)
                raise RuntimeError('synthetic claim crash')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,attempts,lease_generation FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('queued',0,0))
            self.assertEqual(owner.execute('SELECT state FROM wpl.outbox WHERE job_id=%s',(identifier,)).fetchone()[0],'pending')
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_claimed'",(identifier,)).fetchone()[0],0)
        self.assertEqual(self.claim(batch_size=1)[0].job_id,identifier)

    def test_claim_and_renew_recheck_stored_actor_without_trusting_worker_context(self):
        identifier=self.enqueue(actor=self.admin)
        lease=self.claim(batch_size=1)[0]
        with connect() as owner:
            owner.execute("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(self.member,))
        self.assertFalse(renew_delivery(self.worker,self.worker_id,lease))
        self.expire(identifier)
        with self.worker.request_transaction(RequestContext(VerifiedIdentity(self.a['user']),RequestScope.TENANT,self.a['org'])) as session:
            rows=session.execute(text('SELECT * FROM wpl.claim_deliveries(:worker,1,60)'),{'worker':self.worker_id}).all()
            self.assertEqual(rows,[])
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,last_error_code,lease_owner,lease_until FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('cancelled','actor_not_authorized',None,None))
            self.assertEqual(owner.execute("SELECT actor_id FROM wpl.audit_events WHERE target_id=%s AND action='job_cancelled'",(identifier,)).fetchone()[0],self.admin)

    def test_exhausted_expired_lease_dead_letters_without_unbounded_attempts(self):
        identifier=self.enqueue()
        for attempt in range(1,6):
            lease=self.claim(batch_size=1)[0]
            self.assertEqual((lease.job_id,lease.attempts),(identifier,attempt))
            self.expire(identifier)
        self.assertEqual(self.claim(batch_size=1),[])
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,attempts,last_error_code,lease_owner,lease_until FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('dead',5,'attempts_exhausted',None,None))
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE target_id=%s AND action='job_dead'",(identifier,)).fetchone()[0],1)

    def test_available_time_and_batch_limit_are_enforced(self):
        identifiers={self.enqueue() for _ in range(3)}
        leases=self.claim(batch_size=2)
        self.assertEqual(len(leases),2)
        self.assertTrue({lease.job_id for lease in leases}<=identifiers)
        last=(identifiers-{lease.job_id for lease in leases}).pop()
        with connect() as owner:owner.execute("UPDATE wpl.jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE id=%s",(last,))
        # Other synthetic test classes may also have queued rows; only our delayed row is excluded.
        self.assertNotIn(last,{lease.job_id for lease in self.claim(batch_size=20)})

    def test_invalid_bounds_and_direct_privilege_escalation_are_rejected(self):
        self.enqueue()
        for options in ({'batch_size':0},{'batch_size':21},{'batch_size':True},{'lease_seconds':4},{'lease_seconds':301}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.claim(**options)
        with connect('WORKER') as worker:
            with self.assertRaises(psycopg.errors.InvalidParameterValue):
                worker.execute('SELECT * FROM wpl.claim_deliveries(%s,100,60)',(self.worker_id,))
        for statement in ('SELECT * FROM wpl.jobs','SELECT * FROM wpl.secret_payloads',
                          "UPDATE wpl.jobs SET state='succeeded'",'SELECT wpl.delivery_actor_allowed(NULL,NULL)'):
            with self.subTest(operation=statement),self.assertRaises(DBAPIError):
                with self.worker.transaction() as session:session.execute(text(statement))
        with self.assertRaises(DBAPIError) as result:
            with self.app.transaction() as session:
                session.execute(text('SELECT * FROM wpl.claim_deliveries(:worker,1,60)'),{'worker':self.worker_id})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
