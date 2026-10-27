"""Signed HTTP primary/recovery paths use actual runtime functions and grants."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from uuid import UUID,uuid4
from fastapi.testclient import TestClient
from backend.app.foundation.app import create_app
from backend.app.foundation.settings import FoundationSettings
from test_schema import connect
import test_http_platform as platform_fixtures


class TransferHTTPTests(unittest.TestCase):
    setUpClass=classmethod(platform_fixtures.PlatformHTTPTests.setUpClass.__func__)
    setUp=platform_fixtures.PlatformHTTPTests.setUp
    token=platform_fixtures.PlatformHTTPTests.token
    get=platform_fixtures.PlatformHTTPTests.get
    assert_error=platform_fixtures.PlatformHTTPTests.assert_error

    def path(self,*,recovery=False,org=None,preview=False):
        org=org or self.a['org']
        base=f'/v1/platform/organizations/{org}/primary-admin-recovery' if recovery else f'/v1/orgs/{org}/primary-admin-transfers'
        return base+('/preview' if preview else '')

    def version(self):
        with connect() as owner:return owner.execute('SELECT version FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone()[0]

    def post(self,body,*,recovery=False,preview=False,actor=None,org=None,headers=None,auth_time='recent',**claims):
        if auth_time=='recent':claims['auth_time']=int(time.time())
        elif auth_time is not None:claims['auth_time']=auth_time
        token=self.token(actor or self.a['user'],**claims)
        return self.client.post(self.path(recovery=recovery,org=org,preview=preview),json=body,
            headers={'Authorization':'Bearer '+token,**(headers or {})})

    def preview(self,*,recovery=False,actor=None):
        response=self.post({'target_membership_id':str(self.secondary_member),'expected_version':self.version(),
            'reason':'Synthetic signed primary change reason'},recovery=recovery,preview=True,actor=actor)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def confirmation(self,preview):
        return {key:preview[key] for key in ('transfer_id','expected_version','confirmation')}

    def test_primary_http_preview_confirm_and_truthful_redacted_notification_status(self):
        before=self.version();preview=self.preview()
        self.assertEqual(set(preview),{'transfer_id','org_id','from_membership_id','to_membership_id','expected_version','expires_at',
            'confirmation','former_primary_retains_admin','operation'})
        self.assertEqual((preview['operation'],preview['former_primary_retains_admin']),('transfer',True))
        self.assertEqual(preview['from_membership_id'],str(self.a['member']))
        self.assertEqual(preview['to_membership_id'],str(self.secondary_member));self.assertEqual(self.version(),before)
        response=self.post(self.confirmation(preview),headers={'If-Match':'"'+str(before)+'"'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers['Idempotency-Replayed'],'false')
        body=response.json();self.assertEqual((body['version'],body['primary_admin_membership_id']),(before+1,str(self.secondary_member)))
        self.assertEqual(body['delivery_status'],'pending_integration')
        job=self.get(f"/v1/orgs/{self.a['org']}/jobs/{body['job_id']}",self.a['user'])
        self.assertEqual(job.status_code,200,job.text)
        self.assertEqual(set(job.json()),{'job_id','kind','state','delivery_status','attempts','max_attempts','last_error_code','created_at','updated_at'})
        self.assertEqual((job.json()['kind'],job.json()['state'],job.json()['delivery_status']),('notify_primary_transfer','queued','pending_integration'))
        self.assertEqual(job.headers['Cache-Control'],'no-store')
        for value in (preview['confirmation'],'confirmation_hash','intent_hash','key_reference','lease_owner','contact@example.invalid'):
            self.assertNotIn(value,str((body,job.json())))
        replay=self.post(self.confirmation(preview));self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),body);self.assertEqual(replay.headers['Idempotency-Replayed'],'true')
        detail=self.get(f"/v1/orgs/{self.a['org']}",self.secondary).json()
        self.assertEqual(detail['primary_admin_membership_id'],str(self.secondary_member))
        with connect() as owner:
            self.assertIn(('admin',),owner.execute('SELECT role FROM wpl.organization_roles WHERE org_id=%s AND membership_id=%s',(self.a['org'],self.a['member'])).fetchall())
        print('Signed primary HTTP: version-bound confirmation committed; old admin retained; redacted pending notification status and receipt replay passed.',flush=True)

    def test_nonprimary_and_spoofed_actor_role_scope_headers_cannot_gain_transfer_authority(self):
        body={'target_membership_id':str(self.secondary_member),'expected_version':self.version(),'reason':'Synthetic unauthorized request'}
        response=self.client.post(self.path(preview=True),json=body)
        self.assert_error(response,401,'invalid_identity')
        for actor in (self.secondary,self.student,self.teacher,self.executive,self.pending,self.b['user']):
            with self.subTest(actor=str(actor)):
                self.assert_error(self.post(body,preview=True,actor=actor),403,'forbidden')
        response=self.post(body,preview=True,actor=self.student,role='executive',user_metadata={'capabilities':['recovery']},
            headers={'X-Actor-ID':str(self.a['user']),'X-Scope':'tenant','X-Org-ID':str(self.a['org'])})
        self.assert_error(response,403,'forbidden')
        self.assert_error(self.post({**body,'actor_id':str(self.a['user'])},preview=True),422,'validation_error')
        with connect() as owner:self.assertEqual(owner.execute('SELECT count(*) FROM wpl.primary_admin_transfers WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_recent_auth_typed_fields_confirmation_and_if_match_are_enforced_without_echo(self):
        body={'target_membership_id':str(self.secondary_member),'expected_version':self.version(),'reason':'Synthetic validation reason'}
        for auth in (None,int(time.time())-360):
            self.assert_error(self.post(body,preview=True,auth_time=auth),409,'recent_auth_required')
        self.assert_error(self.post(body,preview=True,auth_time=int(time.time())+60),401,'invalid_identity')
        for invalid in ({**body,'expected_version':True},{**body,'expected_version':2**40},{**body,'reason':'Synthetic\nreason'},
            {**body,'target_membership_id':str(UUID(int=0))},{**body,'target_membership_id':'invalid'},
            {**body,'reason':' '},{**body,'scope':'platform'}):
            self.assert_error(self.post(invalid,preview=True),422,'validation_error')
        self.assert_error(self.post(body,preview=True,headers={'If-Match':'"999999"'}),409,'version_conflict')
        preview=self.preview();confirmation=self.confirmation(preview)
        for invalid in ({**confirmation,'expected_version':True},{**confirmation,'confirmation':'secret value with spaces'},
            {**confirmation,'transfer_id':str(UUID(int=0))},{**confirmation,'target_membership_id':str(self.a['member'])}):
            response=self.post(invalid);self.assert_error(response,422,'validation_error')
            self.assertNotIn('secret value with spaces',response.text)
        self.assert_error(self.post({**confirmation,'confirmation':'wrong-confirmation'}),409,'invalid_confirmation')
        self.assert_error(self.post({**confirmation,'transfer_id':str(uuid4())}),409,'invalid_confirmation')
        self.assert_error(self.post(confirmation,auth_time=None),409,'recent_auth_required')
        self.assert_error(self.post(confirmation,headers={'If-Match':'W/"'+str(body['expected_version'])+'"'}),409,'version_conflict')

    def test_concurrent_signed_confirmations_return_one_committed_receipt_and_intent(self):
        preview=self.preview();body=self.confirmation(preview);barrier=threading.Barrier(2)
        def send():barrier.wait(timeout=5);return self.post(body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(send) for _ in range(2)]
            responses=[future.result(timeout=20) for future in futures]
        for response in responses:self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(responses[0].json(),responses[1].json())
        self.assertCountEqual([r.headers['Idempotency-Replayed'] for r in responses],['false','true'])
        with connect() as owner:
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.jobs WHERE org_id=%s AND kind='notify_primary_transfer'",(self.a['org'],)).fetchone()[0],1)
            self.assertEqual(owner.execute("SELECT count(*) FROM wpl.audit_events WHERE org_id=%s AND action='primary_transferred'",(self.a['org'],)).fetchone()[0],1)
        print('Concurrent signed HTTP confirmations: identical receipt, one change and notification intent; DB pool size-two race is separately mandatory.',flush=True)

    def test_stale_target_version_and_current_global_block_reject_cached_token_confirmation(self):
        preview=self.preview();body=self.confirmation(preview)
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='removed' WHERE id=%s",(self.secondary_member,))
        self.assert_error(self.post(body),409,'version_conflict')
        with connect() as owner:owner.execute("UPDATE wpl.organization_memberships SET status='active' WHERE id=%s",(self.secondary_member,))
        preview=self.preview();body=self.confirmation(preview)
        token=self.token(self.a['user'],auth_time=int(time.time()));headers={'Authorization':'Bearer '+token}
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
        self.assert_error(self.client.post(self.path(),json=body,headers=headers),403,'forbidden')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT status,primary_admin_membership_id FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone(),('recovery_required',self.a['member']))
            self.assertEqual(owner.execute('SELECT count(*) FROM wpl.jobs WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)

    def test_explicit_recovery_scope_requires_separate_grant_and_preserves_old_global_block(self):
        with connect() as owner:owner.execute("UPDATE wpl.users SET global_state='suspended' WHERE id=%s",(self.a['user'],))
        body={'target_membership_id':str(self.secondary_member),'expected_version':self.version(),'reason':'Synthetic recovery evidence reference fixture-123'}
        self.assert_error(self.post(body,recovery=True,preview=True,actor=self.executive),403,'forbidden')
        self.assert_error(self.post(body,recovery=True,preview=True,actor=self.secondary),403,'forbidden')
        with connect() as owner:owner.execute("INSERT INTO wpl.platform_roles(user_id,capability,reason) VALUES (%s,'recovery','Synthetic explicit recovery')",(self.observer,))
        preview=self.preview(recovery=True,actor=self.observer)
        self.assertEqual(preview['operation'],'recovery')
        response=self.post(self.confirmation(preview),recovery=True,actor=self.observer)
        self.assertEqual(response.status_code,200,response.text);result=response.json()
        self.assertEqual((result['status'],result['primary_admin_membership_id']),('active',str(self.secondary_member)))
        path=f"/v1/platform/organizations/{self.a['org']}/primary-admin-recovery/jobs/{result['job_id']}"
        job=self.get(path,self.observer);self.assertEqual(job.status_code,200,job.text)
        self.assertEqual(job.json()['delivery_status'],'pending_integration')
        self.assert_error(self.get(path,self.executive),404,'not_found')
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}/members",self.observer),404,'not_found')
        with connect() as owner:
            self.assertEqual(owner.execute('SELECT global_state FROM wpl.users WHERE id=%s',(self.a['user'],)).fetchone()[0],'suspended')
            owner.execute("DELETE FROM wpl.platform_roles WHERE user_id=%s AND capability='recovery'",(self.observer,))
        self.assert_error(self.post(self.confirmation(preview),recovery=True,actor=self.observer),403,'forbidden')
        self.assert_error(self.get(path,self.observer),404,'not_found')

    def test_notification_status_does_not_adopt_wrong_scope_private_or_tampered_jobs(self):
        preview=self.preview();response=self.post(self.confirmation(preview));self.assertEqual(response.status_code,200,response.text)
        identifier=response.json()['job_id'];path=f"/v1/orgs/{self.a['org']}/jobs/{identifier}"
        self.assert_error(self.get(path,self.student),404,'not_found')
        self.assert_error(self.get(path,self.executive),404,'not_found')
        self.assert_error(self.get(f"/v1/orgs/{self.b['org']}/jobs/{identifier}",self.b['user']),404,'not_found')
        self.assert_error(self.get(f"/v1/orgs/{self.a['org']}/jobs/{uuid4()}",self.a['user']),404,'not_found')
        self.assert_error(self.get(f"/v1/platform/organizations/{self.a['org']}/jobs/{identifier}",self.executive),404,'not_found')
        with connect() as owner:owner.execute('UPDATE wpl.jobs SET intent_hash=%s WHERE id=%s',('0'*64,UUID(identifier)))
        self.assert_error(self.get(path,self.a['user']),404,'not_found')
        # Receipt replay describes the committed action, not current notification status.
        self.assertEqual(self.post(self.confirmation(preview)).json(),response.json())

    def test_real_database_failure_is_sanitized_rolls_back_and_pool_retry_then_feature_off(self):
        preview=self.preview();body=self.confirmation(preview)
        with connect() as owner:owner.execute("ALTER TABLE wpl.audit_events ADD CONSTRAINT fixture_http_primary_failure CHECK(action<>'primary_transferred') NOT VALID")
        try:
            response=self.post(body);self.assert_error(response,503,'data_unavailable')
            for marker in (preview['confirmation'],'fixture_http_primary_failure','INSERT','wpl.audit_events'):
                self.assertNotIn(marker,response.text)
            with connect() as owner:
                self.assertEqual(owner.execute('SELECT primary_admin_membership_id FROM wpl.organizations WHERE id=%s',(self.a['org'],)).fetchone()[0],self.a['member'])
                self.assertEqual(owner.execute('SELECT status,result FROM wpl.primary_admin_transfers WHERE id=%s',(UUID(preview['transfer_id']),)).fetchone(),('preview',None))
                self.assertEqual(owner.execute('SELECT count(*) FROM wpl.jobs WHERE org_id=%s',(self.a['org'],)).fetchone()[0],0)
        finally:
            with connect() as owner:owner.execute('ALTER TABLE wpl.audit_events DROP CONSTRAINT fixture_http_primary_failure')
        response=self.post(body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.get('/v1/me',self.a['user']).status_code,200)
        with TestClient(create_app(FoundationSettings())) as disabled:
            for path in (self.path(),self.path(preview=True),self.path(recovery=True),self.path(recovery=True,preview=True)):
                self.assertEqual(disabled.post(path,json=body).status_code,404)
