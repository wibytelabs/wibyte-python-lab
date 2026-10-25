"""Actual executive HTTP/domain writes: expected versions, audit and invariants."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import unittest
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import TenantConflict
from backend.app.domains.organizations.metadata import change_organization
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings
from test_schema import connect
import test_http_platform as platform_fixtures


class ExecutiveMetadataTests(unittest.TestCase):
    setUpClass=classmethod(platform_fixtures.PlatformHTTPTests.setUpClass.__func__)
    setUp=platform_fixtures.PlatformHTTPTests.setUp
    token=platform_fixtures.PlatformHTTPTests.token
    get=platform_fixtures.PlatformHTTPTests.get
    assert_error=platform_fixtures.PlatformHTTPTests.assert_error

    def detail(self,org=None):
        response=self.get('/v1/platform/organizations/'+str(org or self.a['org']),self.executive)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def send(self,body,*,org=None,subject=None,status=False):
        path='/v1/platform/organizations/'+str(org or self.a['org'])
        method=self.client.post if status else self.client.patch
        return method(path+('/status' if status else ''),headers={'Authorization':'Bearer '+self.token(subject or self.executive)},json=body)

    def test_metadata_commit_normalizes_contact_advances_version_and_redacts_audit_values(self):
        before=self.detail()
        response=self.send({'expected_version':before['version'],'reason':'Correct synthetic metadata',
            'name':' Updated synthetic school ','contact_email':' CONTACT2@EXAMPLE.INVALID ','home_region':'ap-south-1'})
        self.assertEqual(response.status_code,200,response.text)
        body=response.json();self.assertEqual(body['version'],before['version']+1)
        self.assertEqual(body['access_epoch'],before['access_epoch'])
        self.assertEqual((body['name'],body['contact_email'],body['home_region']),('Updated synthetic school','contact2@example.invalid','ap-south-1'))
        with connect() as owner:
            row=owner.execute("SELECT actor_id,reason,changes FROM wpl.audit_events WHERE org_id=%s AND action='organization_metadata_changed'",(self.a['org'],)).fetchone()
            self.assertEqual(row[0],self.executive)
            self.assertEqual(set(row[2]['fields']),{'name','contact_email','home_region'})
            self.assertNotIn('contact2@example.invalid',str(row[2]))
            self.assertEqual(owner.execute('SELECT primary_admin_membership_id FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone()[0],self.a['member'])

    def test_status_suspends_and_resumes_with_epoch_audit_and_current_tenant_denial(self):
        before=self.detail()
        body={'expected_version':before['version'],'reason':'Synthetic organization suspension','status':'suspended'}
        response=self.send(body,status=True);self.assertEqual(response.status_code,200,response.text)
        after=response.json();self.assertEqual(after['access_epoch'],before['access_epoch']+1)
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}",self.a['user']),404,'not_found')
        body.update(expected_version=after['version'],status='active',reason='Synthetic organization resume')
        response=self.send(body,status=True);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['access_epoch'],before['access_epoch']+2)
        self.assertEqual(self.get(f"/v1/orgs/{self.a['org']}",self.a['user']).status_code,200)
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='organization_status_changed'",(self.a['org'],)).fetchone()[0],2)

    def test_nonexecutive_pending_expired_and_spoofed_authority_cannot_write(self):
        before=self.detail();body={'expected_version':before['version'],'reason':'Unauthorized synthetic edit','name':'Must not persist'}
        for subject in (self.a['user'],self.student,self.observer,self.pending):
            with self.subTest(subject=str(subject)):self.assert_error(self.send(body,subject=subject),403,'forbidden')
        token=self.token(self.student,role='executive',user_metadata={'capabilities':['orgs']})
        response=self.client.patch(f"/v1/platform/organizations/{self.a['org']}",headers={'Authorization':'Bearer '+token,'X-Actor-ID':str(self.executive)},json=body)
        self.assert_error(response,403,'forbidden')
        with connect() as owner:owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s",(self.executive,))
        self.assert_error(self.send(body),403,'forbidden')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT name,version FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone(),(before['name'],before['version']))

    def test_invalid_fields_versions_reasons_and_unknown_organization_have_stable_errors(self):
        before=self.detail();base={'expected_version':before['version'],'reason':'Synthetic validated edit','name':'Allowed metadata'}
        for body in ({**base,'expected_version':True},{**base,'reason':'     '},{**base,'name':'  '},
                     {**base,'contact_email':'not-email'},{**base,'primary_admin_membership_id':str(uuid4())},
                     {**base,'actor_id':str(self.executive)},{'expected_version':before['version'],'reason':'Missing edit'}):
            self.assert_error(self.send(body),422,'validation_error')
        self.assert_error(self.send({**base,'expected_version':before['version']+1}),409,'version_conflict')
        self.assert_error(self.send(base,org=uuid4()),404,'not_found')
        self.assert_error(self.send({'expected_version':before['version'],'reason':'Use explicit recovery','status':'recovery_required'},status=True),422,'validation_error')

    def test_pending_primary_cannot_activate_and_recovery_cannot_be_bypassed(self):
        with connect() as owner:
            org,member,invite=uuid4(),uuid4(),uuid4()
            owner.execute("""INSERT INTO wpl.organizations(id,name,organization_type,contact_email,home_region,primary_admin_membership_id,provisioning_identity)
                VALUES (%s,'Synthetic unaccepted primary','other','contact@example.invalid','fixture',%s,%s)""",(org,member,str(uuid4())))
            owner.execute("INSERT INTO wpl.organization_memberships(id,org_id,invitation_id,status) VALUES (%s,%s,%s,'invite_pending')",(member,org,invite))
            owner.execute("INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (%s,%s,'admin')",(org,member))
            owner.execute("""INSERT INTO wpl.invitations(id,org_id,membership_id,intended_email,intended_roles,token_hash,expires_at)
                VALUES (%s,%s,%s,'primary@example.invalid',ARRAY['admin'],%s,now()+interval '1 day')""",(invite,org,member,hashlib.sha256(uuid4().bytes).digest()))
        pending=self.detail(org)
        self.assert_error(self.send({'expected_version':pending['version'],'reason':'Cannot skip invitation acceptance','status':'active'},org=org,status=True),409,'primary_not_active')
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
        recovery=self.detail();self.assertEqual(recovery['status'],'recovery_required')
        self.assert_error(self.send({'expected_version':recovery['version'],'reason':'Cannot bypass protected recovery','status':'active'},status=True),409,'recovery_required')

    def test_competing_executives_recheck_locked_expected_version(self):
        before=self.detail();other=uuid4()
        with connect() as owner:
            owner.execute("INSERT INTO wpl.users(id,global_state) VALUES (%s,'active')",(other,))
            owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Synthetic second executive')",(other,))
        db=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=self.database.engine.url,pool_size=2));self.addCleanup(db.close)
        barrier=threading.Barrier(2)
        def run(actor):
            with db.request_transaction(RequestContext(VerifiedIdentity(actor),RequestScope.PLATFORM,self.a['org'])) as session:
                barrier.wait(timeout=5)
                try:
                    change_organization(session,VerifiedIdentity(actor),self.a['org'],version=before['version'],reason='Synthetic competing metadata edit',operation='metadata',name='Race '+str(actor))
                    return 'applied'
                except TenantConflict as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,actor) for actor in (self.executive,other)]
            results=[future.result(timeout=15) for future in futures]
        self.assertCountEqual(results,['applied','version_conflict'])
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='organization_metadata_changed'",(self.a['org'],)).fetchone()[0],1)
        print('Actual wpl_app executive race: one versioned metadata change/audit, one conflict.',flush=True)

    def test_real_audit_constraint_failure_rolls_back_metadata_inside_caught_savepoint(self):
        before=self.detail()
        with connect() as owner:owner.execute("ALTER TABLE wpl.audit_events ADD CONSTRAINT fixture_reject_metadata CHECK(action<>'organization_metadata_changed') NOT VALID")
        try:
            with self.database.request_transaction(RequestContext(VerifiedIdentity(self.executive),RequestScope.PLATFORM,self.a['org'])) as session:
                with self.assertRaises(DBAPIError) as result:
                    change_organization(session,VerifiedIdentity(self.executive),self.a['org'],version=before['version'],reason='Synthetic failing audit',operation='metadata',name='Must roll back')
                self.assertEqual(result.exception.orig.sqlstate,'23514')
                row=session.execute(text('SELECT name,version FROM wpl.organizations WHERE id=:org'),{'org':self.a['org']}).one()
                self.assertEqual(tuple(row),(before['name'],before['version']))
        finally:
            with connect() as owner:owner.execute('ALTER TABLE wpl.audit_events DROP CONSTRAINT fixture_reject_metadata')
        self.assertEqual(self.detail()['version'],before['version'])

    def test_narrow_function_does_not_grant_direct_status_or_unbound_changes_and_noop_is_stable(self):
        before=self.detail();body={'expected_version':before['version'],'reason':'Synthetic unchanged metadata','name':before['name']}
        self.assertEqual(self.send(body).json()['version'],before['version'])
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(RequestContext(VerifiedIdentity(self.executive),RequestScope.PLATFORM,self.a['org'])) as session:
                session.execute(text("UPDATE wpl.organizations SET status='suspended' WHERE id=:org"),{'org':self.a['org']})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
        with self.database.request_transaction(RequestContext(VerifiedIdentity(self.executive),RequestScope.PLATFORM,self.b['org'])) as session:
            result=session.execute(text("SELECT wpl.change_organization(:org,1,'status',NULL,NULL,NULL,'suspended','Synthetic context substitution')"),{'org':self.a['org']}).scalar_one()
            self.assertEqual(result,{'error':'forbidden'})
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='organization_metadata_changed'",(self.a['org'],)).fetchone()[0],0)
