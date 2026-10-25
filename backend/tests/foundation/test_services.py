"""Production domain service tests with synthetic identities and actual Postgres.

Owner sessions here isolate application policy/transaction tests from RLS. Actual
runtime-role RLS/API policy proofs remain P02.3; this is not a substitute for them.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import os
import unittest
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from backend.app.foundation.settings import postgres_url
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import TenantConflict, AuthorizationDenied
from backend.app.domains.organizations.service import set_member_status, replace_roles, complete_primary_transfer
from backend.app.domains.cohorts.service import set_instructors
from test_schema import connect, seed_org
from test_guards import add_member

NOW=datetime(2030,1,1,tzinfo=timezone.utc)


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=postgres_url(os.environ['WPL_MIGRATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':
            raise RuntimeError('Refusing non-fixture service target.')
        cls.engine=create_engine(url,poolclass=NullPool,hide_parameters=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with connect() as owner:
            self.fixture=seed_org(owner)
            self.admin_user,self.admin=add_member(owner,self.fixture['org'])
            self.teacher_user,self.teacher=add_member(owner,self.fixture['org'],('instructor',))
            self.student_user,self.student=add_member(owner,self.fixture['org'],('student',))
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(self.fixture['org'],))
        self.identity=VerifiedIdentity(self.fixture['user'],NOW)
        self.org=self.fixture['org']

    def version(self,session,member):
        return session.execute(text('SELECT version FROM wpl.organization_memberships WHERE org_id=:org AND id=:id'),{'org':self.org,'id':member}).scalar_one()

    def conflict(self,code,fn):
        with self.assertRaises(TenantConflict) as caught:
            fn()
        self.assertEqual(caught.exception.code,code)

    def test_primary_is_protected_through_both_ordinary_service_paths(self):
        with Session(self.engine) as session,session.begin():
            for identity in (self.identity,VerifiedIdentity(self.admin_user,NOW)):
                for status in ('suspended','removed'):
                    self.conflict('protected_primary',lambda: set_member_status(session,identity,self.org,self.fixture['member'],status,
                        self.version(session,self.fixture['member']),'Synthetic protection check'))
                self.conflict('protected_primary',lambda: replace_roles(session,identity,self.org,self.fixture['member'],['student'],
                    self.version(session,self.fixture['member']),'Synthetic protection check'))

    def test_status_changes_commit_rollback_and_append_audit_with_epoch(self):
        with Session(self.engine) as session,session.begin():
            before=session.execute(text('SELECT access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student}).scalar_one()
            result=set_member_status(session,self.identity,self.org,self.student,'suspended',self.version(session,self.student),'Synthetic suspend test')
            self.assertEqual(result['status'],'suspended')
            self.assertGreater(session.execute(text('SELECT access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student}).scalar_one(),before)
        with self.assertRaisesRegex(RuntimeError,'synthetic rollback'):
            with Session(self.engine) as session,session.begin():
                set_member_status(session,self.identity,self.org,self.student,'active',self.version(session,self.student),'Synthetic restore test')
                raise RuntimeError('synthetic rollback')
        with Session(self.engine) as session:
            self.assertEqual(session.execute(text('SELECT status FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student}).scalar_one(),'suspended')
            self.assertEqual(session.execute(text("SELECT count(*) FROM wpl.audit_events WHERE org_id=:org AND action='membership_status_changed'"),{'org':self.org}).scalar_one(),1)

    def test_role_changes_advance_member_epoch_and_never_grant_platform_role(self):
        with Session(self.engine) as session,session.begin():
            before=session.execute(text('SELECT access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student}).scalar_one()
            receipt=replace_roles(session,self.identity,self.org,self.student,['student','instructor'],self.version(session,self.student),'Synthetic role change')
            self.assertEqual(receipt['roles'],['instructor','student'])
            self.assertGreater(session.execute(text('SELECT access_epoch FROM wpl.organization_memberships WHERE id=:id'),{'id':self.student}).scalar_one(),before)
            self.conflict('invalid_roles',lambda: replace_roles(session,self.identity,self.org,self.student,['executive'],receipt['version'],'Synthetic invalid role'))
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.platform_roles WHERE user_id=:id'),{'id':self.student_user}).scalar_one(),0)

    def test_last_instructor_errors_are_clear_and_replacement_retains_history(self):
        with Session(self.engine) as session,session.begin():
            version=session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one()
            first=set_instructors(session,self.identity,self.org,self.fixture['cohort'],[self.teacher],version,'Synthetic initial staffing')
            session.execute(text("UPDATE wpl.cohorts SET status='active' WHERE id=:id"),{'id':self.fixture['cohort']})
            version=session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one()
            self.conflict('last_instructor',lambda: set_instructors(session,self.identity,self.org,self.fixture['cohort'],[],version,'Synthetic staffing removal'))
            self.conflict('last_instructor',lambda: set_member_status(session,self.identity,self.org,self.teacher,'suspended',self.version(session,self.teacher),'Synthetic instructor suspend'))
            self.conflict('last_instructor',lambda: replace_roles(session,self.identity,self.org,self.teacher,['student'],self.version(session,self.teacher),'Synthetic instructor demotion'))
            replace_roles(session,self.identity,self.org,self.student,['instructor'],self.version(session,self.student),'Synthetic replacement eligibility')
            version=session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one()
            epoch=session.execute(text('SELECT access_epoch FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one()
            set_instructors(session,self.identity,self.org,self.fixture['cohort'],[self.student],version,'Synthetic instructor replacement')
            self.assertEqual(session.execute(text("SELECT status FROM wpl.cohort_memberships WHERE org_id=:org AND cohort_id=:cohort AND membership_id=:id AND role='instructor'"),{'org':self.org,'cohort':self.fixture['cohort'],'id':self.teacher}).scalar_one(),'removed')
            self.assertGreater(session.execute(text('SELECT access_epoch FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one(),epoch)

    def test_service_policy_denies_cross_org_nonadmin_pending_and_blocked_actor(self):
        with connect() as owner:
            other=seed_org(owner)
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(other['org'],))
            pending=uuid4()
            owner.execute("INSERT INTO wpl.users(id) VALUES (%s)",(pending,))
        with Session(self.engine) as session,session.begin():
            for actor in (VerifiedIdentity(other['user'],NOW),VerifiedIdentity(self.student_user,NOW),VerifiedIdentity(pending,NOW)):
                with self.subTest(actor=actor.subject),self.assertRaises(AuthorizationDenied):
                    set_member_status(session,actor,self.org,self.teacher,'suspended',self.version(session,self.teacher),'Synthetic denied change')
            session.execute(text("UPDATE wpl.users SET global_state='suspended' WHERE id=:id"),{'id':self.admin_user})
            with self.assertRaises(AuthorizationDenied):
                set_member_status(session,VerifiedIdentity(self.admin_user,NOW),self.org,self.teacher,'suspended',self.version(session,self.teacher),'Synthetic blocked actor')

    def test_stale_version_and_cross_org_instructor_have_no_side_effect(self):
        with connect() as owner:
            other=seed_org(owner)
            _,other_teacher=add_member(owner,other['org'],('instructor',))
        with Session(self.engine) as session,session.begin():
            self.conflict('version_conflict',lambda: set_member_status(session,self.identity,self.org,self.student,'suspended',0,'Synthetic stale request'))
            version=session.execute(text('SELECT version FROM wpl.cohorts WHERE id=:id'),{'id':self.fixture['cohort']}).scalar_one()
            self.conflict('instructor_ineligible',lambda: set_instructors(session,self.identity,self.org,self.fixture['cohort'],[other_teacher],version,'Synthetic cross-org request'))
            self.assertEqual(session.execute(text('SELECT count(*) FROM wpl.audit_events WHERE org_id=:org'),{'org':self.org}).scalar_one(),0)

    def preview(self,session,target=None):
        target=self.admin if target is None else target
        version=session.execute(text('SELECT version FROM wpl.organizations WHERE id=:id'),{'id':self.org}).scalar_one()
        transfer=uuid4()
        session.execute(text("""INSERT INTO wpl.primary_admin_transfers(id,org_id,actor_id,from_membership_id,to_membership_id,
            expected_version,confirmation_hash,status,expires_at) VALUES (:id,:org,:actor,:source,:target,:version,:hash,'preview',:expires)"""),
            {'id':transfer,'org':self.org,'actor':self.identity.subject,'source':self.fixture['member'],'target':target,
             'version':version,'hash':hashlib.sha256(b'synthetic-confirmation').digest(),'expires':NOW+timedelta(minutes=5)})
        return transfer,version

    def test_transfer_checks_confirmation_recent_auth_version_and_keeps_old_admin(self):
        with Session(self.engine) as session,session.begin():
            transfer,version=self.preview(session)
            self.conflict('invalid_confirmation',lambda: complete_primary_transfer(session,self.identity,self.org,transfer,'wrong',version,clock=lambda:NOW))
            self.conflict('recent_auth_required',lambda: complete_primary_transfer(session,VerifiedIdentity(self.identity.subject,NOW-timedelta(minutes=6)),self.org,transfer,'synthetic-confirmation',version,clock=lambda:NOW))
            self.conflict('version_conflict',lambda: complete_primary_transfer(session,self.identity,self.org,transfer,'synthetic-confirmation',version+1,clock=lambda:NOW))
            receipt=complete_primary_transfer(session,self.identity,self.org,transfer,'synthetic-confirmation',version,clock=lambda:NOW)
            self.assertEqual(receipt['primary_admin_membership_id'],self.admin)
            self.assertEqual(session.execute(text("SELECT count(*) FROM wpl.organization_roles WHERE org_id=:org AND membership_id=:member AND role='admin'"),{'org':self.org,'member':self.fixture['member']}).scalar_one(),1)
            self.assertEqual(session.execute(text('SELECT status FROM wpl.primary_admin_transfers WHERE id=:id'),{'id':transfer}).scalar_one(),'completed')
            self.assertNotIn('synthetic-confirmation',session.execute(text('SELECT changes::text FROM wpl.audit_events WHERE org_id=:org'),{'org':self.org}).scalar_one())

    def test_transfer_rejects_ordinary_admin_expired_preview_and_ineligible_target(self):
        with Session(self.engine) as session,session.begin():
            transfer,version=self.preview(session,target=self.student)
            with self.assertRaises(AuthorizationDenied):
                complete_primary_transfer(session,VerifiedIdentity(self.admin_user,NOW),self.org,transfer,'synthetic-confirmation',version,clock=lambda:NOW)
            self.conflict('target_ineligible',lambda: complete_primary_transfer(session,self.identity,self.org,transfer,'synthetic-confirmation',version,clock=lambda:NOW))
            session.execute(text('UPDATE wpl.primary_admin_transfers SET expires_at=:expired WHERE id=:id'),{'id':transfer,'expired':NOW-timedelta(seconds=1)})
            self.conflict('invalid_confirmation',lambda: complete_primary_transfer(session,self.identity,self.org,transfer,'synthetic-confirmation',version,clock=lambda:NOW))
