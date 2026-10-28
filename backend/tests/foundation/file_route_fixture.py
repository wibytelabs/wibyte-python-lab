"""Isolated real route/service/adapter/helper contracts with a local fake Docker transport."""
import io
import json
import os
import secrets
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Annotated
from urllib.parse import quote
from fastapi import Depends,FastAPI,Header,HTTPException
from fastapi.testclient import TestClient

# Only identity/provider and Docker transport are replaced. Actual route, service,
# command adapter, staged data and stdlib helper implementations execute unchanged.
@dataclass
class User:
    id: str


def identity(authorization: Annotated[str | None,Header()]=None):
    if authorization=='Bearer synthetic-owner':return User('owner')
    if authorization=='Bearer synthetic-other':return User('other')
    raise HTTPException(401,'Authentication required')

auth=types.ModuleType('backend.app.auth');auth.CurrentUser=Annotated[User,Depends(identity)]
lab=types.ModuleType('backend.app.services.lab_service')
lab.lab_service=SimpleNamespace(get_for_student=lambda lab_id,user:SimpleNamespace(container_id='synthetic-container') if lab_id=='owned' and user=='owner' else None,
    update_activity=lambda _lab:None)
sys.modules['backend.app.auth']=auth;sys.modules['backend.app.services.lab_service']=lab
from backend.app.runtime import container_files as adapter
from backend.app.routes import workspace
from backend.app.services.workspace_service import WorkspaceService


class FakeContainer:
    def __init__(self,root):
        self.root=root;self.calls=[];self.stages=[];self.fail_action=None;self.fail_archive=False;self.fail_cleanup=False

    def exec_run(self,command,*,user,demux):
        self.calls.append((command,user,demux))
        if command[:3]!=[adapter.PYTHON,'-I','-c']:raise AssertionError('Trusted isolated Python argv required')
        actual=[sys.executable,*command[1:]]
        if command[3]==adapter.SOURCE:
            if user!='student':raise AssertionError('Workspace code must execute as student')
            if command[5]!=adapter.ROOT:raise AssertionError('Server-selected root changed')
            actual[5]=str(self.root)
            if self.fail_action==command[4]:return SimpleNamespace(exit_code=99,output=(b'',b'synthetic-private-runtime-diagnostic'))
        elif command[3] in (adapter.STAGE_SCRIPT,adapter.CLEANUP_SCRIPT):
            if user!='root':raise AssertionError('Staging must be root-owned, never student-writable extraction')
        else:raise AssertionError('Unexpected executable source')
        if command[3]==adapter.CLEANUP_SCRIPT and self.fail_cleanup:return SimpleNamespace(exit_code=15,output=(b'',b''))
        result=subprocess.run(actual,capture_output=True,timeout=10)
        if command[3]==adapter.STAGE_SCRIPT and result.returncode==0:
            self.stages.append((command[4],command[5],json.loads(result.stdout)))
        return SimpleNamespace(exit_code=result.returncode,output=(result.stdout,result.stderr))

    def put_archive(self,directory,archive):
        if self.fail_archive:return False
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r') as tar:
            members=tar.getmembers()
            if len(members)!=1 or members[0].name!='payload' or not members[0].isfile():raise AssertionError('Only owned payload may be extracted')
            data=tar.extractfile(members[0]).read()
            descriptor=os.open(Path(directory)/'payload',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
            try:os.write(descriptor,data)
            finally:os.close(descriptor)
        return True

    def cleanup(self):
        for name,token,expected in self.stages:
            if os.path.lexists('/tmp/'+name):
                subprocess.run([sys.executable,'-I','-c',adapter.CLEANUP_SCRIPT,name,token,json.dumps(expected)],capture_output=True,timeout=5)


class FileRoutes(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.base=Path(self.directory.name);self.root=self.base/'workspace';self.root.mkdir()
        self.outside=self.base/'outside';self.outside.mkdir();(self.outside/'private').write_bytes(b'outside fixture')
        self.container=FakeContainer(self.root);self.addCleanup(self.container.cleanup)
        self.gets=[]
        def get(identifier):self.gets.append(identifier);return self.container
        self.service=WorkspaceService(SimpleNamespace(containers=SimpleNamespace(get=get)))
        workspace.router.workspace_service=self.service
        self.activity=[];lab.lab_service.update_activity=lambda lab_id:self.activity.append(lab_id)
        app=FastAPI();app.include_router(workspace.router)
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer synthetic-owner'}

    def request(self,method,path,**kwargs):return self.client.request(method,'/labs/owned/'+path,headers=self.headers,**kwargs)
    def stage_gone(self):self.assertTrue(all(not os.path.lexists('/tmp/'+name) for name,_token,_expected in self.container.stages))

    def test_normal_general_routes_keep_response_shapes_and_execute_the_real_adapter(self):
        self.assertEqual(self.request('POST','files',json={'path':'course','type':'directory'}).json(),{'path':'course','type':'directory','status':'created'})
        self.assertEqual(self.request('POST','files',json={'path':'course/main.py'}).status_code,200)
        result=self.request('PUT','files/course/main.py',json={'content':'print("π")\n'})
        self.assertEqual(result.json(),{'path':'course/main.py','status':'saved'})
        self.assertEqual(self.request('GET','files/course/main.py').json(),{'path':'course/main.py','content':'print("π")\n'})
        self.assertEqual(self.request('GET','files',params={'path':'course'}).json(),{'path':'course','files':[{'name':'main.py','type':'file'}]})
        self.assertEqual(self.request('POST','files/rename',json={'old_path':'course','new_path':'archive/course'}).status_code,200)
        self.assertEqual(self.request('DELETE','files/archive').json(),{'path':'archive','status':'deleted'})
        self.stage_gone()
        self.assertTrue(any(call[0][3]==adapter.SOURCE for call in self.container.calls))
        self.assertTrue(all(call[0][:3]==[adapter.PYTHON,'-I','-c'] for call in self.container.calls))

    def test_missing_identity_or_foreign_lab_never_resolves_a_container(self):
        endpoints=[('GET','files',{}),('GET','files/a',{}),('PUT','files/a',{'json':{'content':'x'}}),
            ('POST','files',{'json':{'path':'a'}}),('POST','files/rename',{'json':{'old_path':'a','new_path':'b'}}),
            ('DELETE','files/a',{}),('POST','upload?path=a',{'content':b'x'}),('GET','download?path=a',{})]
        for method,path,options in endpoints:
            for headers,expected in (({},401),({'Authorization':'Bearer synthetic-other'},404)):
                response=self.client.request(method,'/labs/owned/'+path,headers=headers,**options)
                self.assertEqual(response.status_code,expected)
        self.assertEqual(self.gets,[]);self.assertEqual(self.container.calls,[])

    def test_root_traversal_absolute_git_and_invalid_paths_fail_for_actual_general_routes(self):
        for path in ('.','../outside/private','/tmp/private','.git/config','course/.git/config','a\\b','a//b'):
            self.assertEqual(self.request('POST','files',json={'path':path}).status_code,400)
            self.assertEqual(self.request('POST','files/rename',json={'old_path':path,'new_path':'new'}).status_code,400)
            self.assertEqual(self.request('POST','files/rename',json={'old_path':'old','new_path':path}).status_code,400)
        self.assertEqual((self.outside/'private').read_bytes(),b'outside fixture')
        self.assertEqual(self.request('GET','files').json()['files'],[])
        self.assertEqual(self.container.stages,[])

    def test_symlink_parents_and_targets_cannot_read_write_delete_rename_or_transfer_outside(self):
        (self.root/'link').symlink_to(self.outside,target_is_directory=True)
        (self.root/'target').symlink_to(self.outside/'private')
        requests=[('GET','files/link/private',{}),('PUT','files/link/private',{'json':{'content':'bad'}}),
            ('DELETE','files/target',{}),('POST','files/rename',{'json':{'old_path':'target','new_path':'new'}}),
            ('POST','upload?path=link/private',{'content':b'bad'}),('GET','download?path=target',{})]
        for method,path,options in requests:self.assertIn(self.request(method,path,**options).status_code,(400,409))
        self.assertEqual((self.outside/'private').read_bytes(),b'outside fixture');self.stage_gone()

    def test_ten_mib_limit_is_413_on_read_editor_rename_delete_list_upload_and_download(self):
        with open(self.root/'large','wb') as stream:stream.truncate(adapter.LIMIT+1)
        for method,path,options in [('GET','files/large',{}),('PUT','files/large',{'json':{'content':'small'}}),
            ('POST','files/rename',{'json':{'old_path':'large','new_path':'renamed'}}),('DELETE','files/large',{}),
            ('GET','files',{}),('GET','download?path=large',{}),('POST','upload?path=new',{'content':b'x'*(adapter.LIMIT+1)})]:
            self.assertEqual(self.request(method,path,**options).status_code,413)
        self.assertEqual(self.request('PUT','files/new',json={'content':'x'*(adapter.LIMIT+1)}).status_code,413)
        self.assertEqual((self.root/'large').stat().st_size,adapter.LIMIT+1);self.assertFalse((self.root/'new').exists());self.stage_gone()

    def test_nonregular_and_hardlinked_files_are_denied_by_general_and_transfer_callers(self):
        os.mkfifo(self.root/'fifo');(self.root/'hard').hardlink_to(self.outside/'private')
        for name in ('fifo','hard'):
            for method,path in [('GET','files/'+name),('DELETE','files/'+name),('GET','download?path='+name)]:self.assertEqual(self.request(method,path).status_code,400)
        self.assertEqual((self.outside/'private').read_bytes(),b'outside fixture')

    def test_create_and_rename_conflicts_preserve_existing_bytes_with_409(self):
        self.service.create_file('synthetic-container','source');self.service.write_file('synthetic-container','source','source bytes')
        self.service.create_file('synthetic-container','target');self.service.write_file('synthetic-container','target','target bytes')
        self.assertEqual(self.request('POST','files',json={'path':'source'}).status_code,409)
        self.assertEqual(self.request('POST','files/rename',json={'old_path':'source','new_path':'target'}).status_code,409)
        self.assertEqual((self.root/'source').read_bytes(),b'source bytes');self.assertEqual((self.root/'target').read_bytes(),b'target bytes');self.stage_gone()

    def test_upload_download_keep_raw_bytes_content_headers_and_activity_only_after_success(self):
        data=b'\x00binary\xff\n';name='space quoted ".bin'
        result=self.request('POST','upload',params={'path':name},content=data)
        self.assertEqual(result.json(),{'status':'uploaded','path':name})
        result=self.request('GET','download',params={'path':name})
        self.assertEqual(result.content,data);self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertEqual(result.headers['x-content-type-options'],'nosniff')
        self.assertEqual(result.headers['content-type'],'application/octet-stream')
        self.assertIn("filename*=UTF-8''"+quote(name,safe=''),result.headers['content-disposition'])
        self.assertEqual(self.activity,['owned','owned'])
        self.assertEqual(self.request('POST','upload',params={'path':name},content=b'new').status_code,409)
        self.assertEqual((self.root/name).read_bytes(),data);self.assertEqual(self.activity,['owned','owned']);self.stage_gone()

    def test_staging_or_helper_failure_cleans_owned_resources_and_returns_no_raw_diagnostics(self):
        (self.root/'editor').write_bytes(b'old')
        for failure in ('archive','write'):
            self.container.fail_archive=failure=='archive';self.container.fail_action='write' if failure=='write' else None
            response=self.request('PUT','files/editor',json={'content':'new'})
            self.assertEqual(response.status_code,500);self.assertNotIn('synthetic-private-runtime-diagnostic',response.text)
            self.assertEqual((self.root/'editor').read_bytes(),b'old');self.stage_gone()

    def test_staging_cleanup_refuses_unexpected_entry_and_wrong_directory_identity(self):
        token=secrets.token_hex(16);name='wpl-files-'+token
        result=self.container.exec_run([adapter.PYTHON,'-I','-c',adapter.STAGE_SCRIPT,name,token],user='root',demux=True)
        self.assertEqual(result.exit_code,0);expected=json.loads(result.output[0]);directory=Path('/tmp')/name
        foreign=directory/'foreign';foreign.write_bytes(b'preserve foreign')
        command=[adapter.PYTHON,'-I','-c',adapter.CLEANUP_SCRIPT,name,token,json.dumps(expected)]
        result=self.container.exec_run(command,user='root',demux=True);self.assertEqual(result.exit_code,15)
        self.assertEqual(foreign.read_bytes(),b'preserve foreign');foreign.unlink()
        command[-1]=json.dumps([expected[0],expected[1]+1,expected[2]])
        self.assertEqual(self.container.exec_run(command,user='root',demux=True).exit_code,15)
        self.assertTrue((directory/'.owner').exists());self.container.cleanup();self.assertFalse(directory.exists())

    def test_completed_write_reports_cleanup_failure_truthfully_and_partial_stage_initialization_is_removed(self):
        (self.root/'editor').write_bytes(b'old')
        self.container.fail_cleanup=True
        response=self.request('PUT','files/editor',json={'content':'new'})
        self.assertEqual(response.status_code,500);self.assertIn('File operation completed',response.json()['detail'])
        self.assertEqual((self.root/'editor').read_bytes(),b'new')
        self.container.fail_cleanup=False;self.container.cleanup();self.stage_gone()
        token=secrets.token_hex(16);name='wpl-files-'+token
        # Inject one actual marker write failure into the unchanged creation script.
        prefix="import os,errno\ndef failed_write(*args): raise OSError(errno.ENOSPC,'synthetic')\nos.write=failed_write\n"
        result=subprocess.run([sys.executable,'-I','-c',prefix+adapter.STAGE_SCRIPT,name,token],capture_output=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertFalse(Path('/tmp',name).exists())

    def test_http_missing_file_type_errors_and_shell_characters_preserve_bounded_contract(self):
        self.assertEqual(self.request('GET','files/missing').status_code,404)
        self.assertEqual(self.request('DELETE','files/missing').status_code,404)
        self.assertEqual(self.request('POST','files',json={'path':'a','type':'device'}).status_code,400)
        name="quotes ; $(touch escaped) ' file.py"
        self.assertEqual(self.request('POST','files',json={'path':name}).status_code,200)
        self.assertEqual(self.request('PUT','files/'+quote(name,safe=''),json={'content':'print(1)'}).status_code,200)
        self.assertEqual((self.root/name).read_text(),'print(1)');self.assertFalse((self.root/'escaped').exists());self.stage_gone()

    def test_actual_routes_have_no_legacy_config_import_or_provider_dependency_in_transport_fixture(self):
        self.assertNotIn('backend.app.config',sys.modules);self.assertNotIn('backend.app.main',sys.modules)
        (self.root/'.git').mkdir();(self.root/'.git'/'config').write_bytes(b'private git fixture')
        self.assertEqual(self.request('POST','files',json={'path':'.gitignore'}).status_code,200)
        self.assertEqual(self.request('GET','files').json()['files'],[{'name':'.gitignore','type':'file'}])
        for command,user,demux in self.container.calls:
            self.assertTrue(demux)
            if command[3]==adapter.SOURCE:self.assertEqual(user,'student')
            else:self.assertEqual(user,'root')
        print('Actual workspace and transfer routes/service/adapter executed shared descriptor helper via isolated Python argv; owner denial, safe paths, byte/header semantics and owned staging cleanup passed.',flush=True)


if __name__=='__main__':
    case=sys.argv[1]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([FileRoutes(case)]))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
