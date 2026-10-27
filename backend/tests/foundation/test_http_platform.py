"""Real identity verification and runtime-role HTTP executive/job read matrix."""
import unittest
from uuid import uuid4
from sqlalchemy import text
from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.errors import AuthorizationDenied
from backend.app.domains.organizations.directory import require_organization_directory
from backend.app.domains.jobs.enqueue import prepare_invitation,enqueue_invitation
from backend.app.domains.jobs.payloads import PayloadCipher
from test_schema import connect
from test_guards import add_member
from test_enqueue import invitation,SyntheticKeys
import test_http as http_fixtures


class PlatformHTTPTests(unittest.TestCase):
    setUpClass=classmethod(http_fixtures.HTTPTests.setUpClass.__func__)
    token=http_fixtures.HTTPTests.token
    get=http_fixtures.HTTPTests.get
    assert_error=http_fixtures.HTTPTests.assert_error

    def setUp(self):
        http_fixtures.HTTPTests.setUp(self)
        self.prefix='Directory-'+uuid4().hex
        with connect() as owner:
            self.executive=uuid4();self.observer=uuid4();self.pending=uuid4()
            for subject,state in ((self.executive,'active'),(self.observer,'active'),(self.pending,'pending')):
                owner.execute('INSERT INTO wpl.users(id,global_state) VALUES (%s,%s)',(subject,state))
            for subject,capability in ((self.executive,'orgs'),(self.observer,'observe'),(self.pending,'orgs')):
                owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,%s,'Explicit synthetic HTTP fixture')",(subject,capability))
            owner.execute('UPDATE wpl.organizations SET name=%s WHERE id=%s',(self.prefix+' Alpha',self.a['org']))
            owner.execute("UPDATE wpl.organizations SET name=%s,organization_type='university',status='suspended' WHERE id=%s",(self.prefix+' Beta',self.b['org']))
            self.secondary,self.secondary_member=add_member(owner,self.a['org'],('admin',))
        self.database=self.app.state.foundation_database

    def enqueue(self):
        with connect() as owner:payload=invitation(owner,self.a['org'])
        identifier=uuid4()
        context=RequestContext(VerifiedIdentity(self.a['user']),RequestScope.TENANT,self.a['org'])
        prepared=prepare_invitation(context,identifier,PayloadCipher(SyntheticKeys(self.database)),payload)
        with self.database.request_transaction(context) as session:enqueue_invitation(session,context,prepared)
        return identifier,payload

    def test_executive_directory_pagination_filter_and_explicit_detail(self):
        path='/v1/platform/organizations';seen=[];cursor=None
        for _ in range(3):
            params={'search':self.prefix,'limit':1}
            if cursor:params['cursor']=cursor
            response=self.get(path,self.executive,params=params)
            self.assertEqual(response.status_code,200,response.text)
            body=response.json();seen.extend(item['id'] for item in body['items'])
            for item in body['items']:
                self.assertEqual(set(item),{'id','name','organization_type','home_region','status','version','created_at'})
            cursor=body['next_cursor']
            if cursor is None:break
        self.assertIsNone(cursor)
        self.assertEqual(set(seen),{str(self.a['org']),str(self.b['org'])})
        self.assertEqual(len(seen),2)
        response=self.get(path,self.executive,params={'search':self.prefix,'status':'suspended','organization_type':'university'})
        self.assertEqual([row['id'] for row in response.json()['items']],[str(self.b['org'])])
        detail=self.get(f"{path}/{self.b['org']}",self.executive)
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['status'],'suspended')
        self.assertEqual(detail.json()['primary_admin_membership_id'],str(self.b['member']))
        self.assertIn('contact_email',detail.json())
        self.assertNotIn('provisioning_identity',detail.json())
        self.assertNotIn('members',detail.json())

    def test_platform_reads_require_actual_current_capability_not_admin_or_metadata(self):
        path='/v1/platform/organizations'
        self.assert_error(self.get(path),401,'invalid_identity')
        for subject in (self.a['user'],self.teacher,self.student,self.observer,self.pending,uuid4()):
            with self.subTest(subject=str(subject)):
                self.assert_error(self.get(path,subject,headers={'X-Actor-ID':str(self.executive),'X-Role':'executive'}),403,'forbidden')
        token=self.token(self.student,role='executive',user_metadata={'capabilities':['orgs'],'approved':True})
        self.assert_error(self.client.get(path,headers={'Authorization':'Bearer '+token}),403,'forbidden')
        self.assert_error(self.get(f"{path}/{self.a['org']}",self.student),403,'forbidden')

    def test_expired_removed_and_suspended_executive_grants_block_cached_tokens(self):
        path='/v1/platform/organizations';headers={'Authorization':'Bearer '+self.token(self.executive)}
        for kind in ('expired','removed','suspended'):
            with self.subTest(kind=kind):
                with connect() as owner:
                    owner.execute("UPDATE wpl.users SET global_state='active' WHERE id=%s",(self.executive,))
                    owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'orgs','Synthetic restore') ON CONFLICT(user_id,capability) DO UPDATE SET expires_at=NULL",(self.executive,))
                self.assertEqual(self.client.get(path,headers=headers).status_code,200)
                with connect() as owner:
                    if kind=='expired':owner.execute("UPDATE wpl.platform_roles SET expires_at=now()-interval '1 second' WHERE user_id=%s",(self.executive,))
                    elif kind=='removed':owner.execute('DELETE FROM wpl.platform_roles WHERE user_id=%s',(self.executive,))
                    else:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.executive,))
                self.assert_error(self.client.get(path,headers=headers),403,'forbidden')
        self.assertEqual(self.database.engine.pool.checkedout(),0)

    def test_directory_bounds_cursor_literal_search_and_context_substitution(self):
        path='/v1/platform/organizations'
        for params,status,code in (({'limit':101},422,'validation_error'),({'cursor':'bad'},400,'invalid_cursor'),
                ({'status':'invented'},422,'validation_error'),({'organization_type':'invented'},422,'validation_error'),
                ({'search':'x'*121},422,'validation_error')):
            self.assert_error(self.get(path,self.executive,params=params),status,code)
        response=self.get(path,self.executive,params={'search':self.prefix+'%'})
        self.assertEqual(response.json()['items'],[])
        self.assert_error(self.get(path+'/not-a-uuid',self.executive),422,'validation_error')
        self.assert_error(self.get(path+'/'+str(uuid4()),self.executive),404,'not_found')
        for context in (RequestContext(VerifiedIdentity(self.student),RequestScope.PLATFORM),
                        RequestContext(VerifiedIdentity(self.executive),RequestScope.TENANT,self.a['org'])):
            with self.assertRaises(AuthorizationDenied):
                with self.database.request_transaction(context) as session:require_organization_directory(session,VerifiedIdentity(self.executive))

    def test_job_projection_preserves_queued_simulated_and_acceptance_without_secrets(self):
        identifier,payload=self.enqueue();path=f"/v1/orgs/{self.a['org']}/jobs/{identifier}"
        response=self.get(path,self.a['user'])
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(set(response.json()),{'job_id','kind','state','delivery_status','attempts','max_attempts','last_error_code','created_at','updated_at'})
        self.assertEqual((response.json()['state'],response.json()['delivery_status']),('queued','pending_integration'))
        for marker in (payload['email'],payload['activation_token'],'ciphertext','private_payload','key_reference','intent_hash','dedup_key','lease_owner'):
            self.assertNotIn(marker,response.text)
        # Projection fixtures only: actual fake adapter execution was proved in P02.4.
        for display in ('simulated','provider_accepted'):
            with connect() as owner:owner.execute("UPDATE wpl.jobs SET state='succeeded',delivery_status=%s WHERE id=%s",(display,identifier))
            body=self.get(path,self.a['user']).json()
            self.assertEqual(body['delivery_status'],display)
            self.assertNotIn('Delivered',str(body))

    def test_job_cross_org_unknown_student_and_executive_reads_share_not_found(self):
        identifier,payload=self.enqueue();path=f"/v1/orgs/{self.a['org']}/jobs/{identifier}"
        for subject in (self.student,self.teacher,self.executive,self.pending,self.b['user'],uuid4()):
            with self.subTest(subject=str(subject)):
                self.assert_error(self.get(path,subject,headers={'X-Actor-ID':str(self.a['user']),'X-Org-ID':str(self.a['org'])}),404,'not_found')
        self.assertEqual(self.get(path,self.secondary).status_code,200)
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}/jobs/{uuid4()}",self.a['user']),404,'not_found')
        self.assert_error(self.get(f"/v1/orgs/{self.b['org']}/jobs/{identifier}",self.a['user']),404,'not_found')
        self.assert_error(self.get(path),401,'invalid_identity')

    def test_job_cached_token_member_and_global_suspension_block_next_request(self):
        identifier,payload=self.enqueue();path=f"/v1/orgs/{self.a['org']}/jobs/{identifier}"
        headers={'Authorization':'Bearer '+self.token(self.secondary)}
        self.assertEqual(self.client.get(path,headers=headers).status_code,200)
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='suspended' WHERE id=%s",(self.secondary_member,))
        self.assert_error(self.client.get(path,headers=headers),404,'not_found')
        with connect() as owner:
            owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.secondary_member,))
            owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.secondary,))
        self.assert_error(self.client.get(path,headers=headers),404,'not_found')
        self.assertEqual(self.database.engine.pool.checkedout(),0)

    def test_directory_capability_never_enters_tenant_roster_or_jobs_and_invalid_posts_cannot_mutate(self):
        identifier,payload=self.enqueue()
        self.assertEqual(self.get('/v1/platform/organizations',self.executive).status_code,200)
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}/members",self.executive),404,'not_found')
        for path in ('/v1/platform/organizations',f"/v1/orgs/{self.a['org']}/jobs/{identifier}"):
            response=self.client.post(path,headers={'Authorization':'Bearer '+self.token(self.executive)},json={'role':'admin'})
            self.assertEqual(response.status_code,405 if '/jobs/' in path else 422,response.text)
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT state,delivery_status FROM wpl.jobs WHERE id=%s',(identifier,)).fetchone(),('queued','pending_integration'))
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.organization_memberships WHERE user_id=%s',(self.executive,)).fetchone()[0],0)
