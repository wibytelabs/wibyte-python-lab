"""Trusted source/argv adapter; root staging never operates on a student path."""
import io
import json
from pathlib import Path
import secrets
import tarfile
from backend.app.runtime import file_ops

ROOT='/workspace/wibyte-workspace'
PYTHON='/usr/local/bin/python'
SOURCE=Path(file_ops.__file__).read_text()
LIMIT=file_ops.LIMIT

class WorkspaceLimitError(ValueError):pass
class WorkspaceConflictError(RuntimeError):pass
class WorkspaceOperationError(RuntimeError):pass
class WorkspaceCleanupError(WorkspaceOperationError):pass

STAGE_SCRIPT=r'''
import json,os,stat,sys
name,token=sys.argv[1:]
if name!='wpl-files-'+token or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):sys.exit(15)
parent=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
folder=None;owned=None;marker_owned=None
try:
    os.mkdir(name,0o711,dir_fd=parent)
    owned=os.stat(name,dir_fd=parent,follow_symlinks=False)
    folder=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    owned=os.fstat(folder)
    os.fchmod(folder,0o711)
    marker=os.open('.owner',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=folder)
    try:
        marker_owned=os.fstat(marker)
        data=token.encode('ascii')
        while data:
            written=os.write(marker,data)
            if written<=0:raise OSError('staging initialization failed')
            data=data[written:]
    finally:os.close(marker)
    print(json.dumps([owned.st_dev,owned.st_ino,owned.st_uid]))
except BaseException:
    # Initialization has not returned ownership to the adapter. Remove only the
    # exact directory/marker this script created; never an unexpected replacement.
    try:
        if owned is not None:
            if folder is None:names=set()
            else:
                with os.scandir(folder) as entries:names={entry.name for entry in entries}
            if names<={'.owner'}:
                if marker_owned is not None and '.owner' in names:
                    current=os.stat('.owner',dir_fd=folder,follow_symlinks=False)
                    if (current.st_dev,current.st_ino,stat.S_IFMT(current.st_mode))==(marker_owned.st_dev,marker_owned.st_ino,stat.S_IFMT(marker_owned.st_mode)):
                        os.unlink('.owner',dir_fd=folder)
                current=os.stat(name,dir_fd=parent,follow_symlinks=False)
                if (current.st_dev,current.st_ino,current.st_uid)==(owned.st_dev,owned.st_ino,owned.st_uid):os.rmdir(name,dir_fd=parent)
    except OSError:pass
    raise
finally:
    if folder is not None:os.close(folder)
    os.close(parent)
'''
CLEANUP_SCRIPT=r'''
import json,os,stat,sys
name,token,encoded=sys.argv[1:]
if name!='wpl-files-'+token or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):sys.exit(15)
expected=json.loads(encoded)
parent=os.open('/tmp',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    folder=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
    try:
        info=os.fstat(folder)
        if [info.st_dev,info.st_ino,info.st_uid]!=expected or info.st_uid!=os.geteuid():sys.exit(15)
        marker=os.open('.owner',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder)
        try:
            item=os.fstat(marker)
            if not stat.S_ISREG(item.st_mode) or item.st_nlink!=1 or item.st_uid!=os.geteuid() or os.read(marker,33)!=token.encode('ascii'):sys.exit(15)
        finally:os.close(marker)
        with os.scandir(folder) as entries:names={entry.name for entry in entries}
        if names-{'payload','.owner'}:sys.exit(15)
        if 'payload' in names:
            item=os.stat('payload',dir_fd=folder,follow_symlinks=False)
            if not stat.S_ISREG(item.st_mode) or item.st_nlink!=1 or item.st_uid!=os.geteuid() or item.st_size>10*1024*1024:sys.exit(15)
            os.unlink('payload',dir_fd=folder)
        os.unlink('.owner',dir_fd=folder)
    finally:os.close(folder)
    current=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if [current.st_dev,current.st_ino,current.st_uid]!=expected:sys.exit(15)
    os.rmdir(name,dir_fd=parent)
finally:os.close(parent)
'''


def checked(result):
    code=result.exit_code
    if code==10:raise ValueError('Invalid or protected workspace path.')
    if code==11:raise FileExistsError('A file or directory with that name already exists.')
    if code==12:raise FileNotFoundError('File or directory not found.')
    if code==13:raise WorkspaceLimitError('Maximum file size is 10 MB; directory traversal is also bounded.')
    if code==14:raise WorkspaceConflictError('Workspace changed. Reload before retrying.')
    if code!=0:raise WorkspaceOperationError('Workspace operation failed.')
    output=result.output
    if not isinstance(output,tuple) or len(output)!=2:raise WorkspaceOperationError('Workspace operation failed.')
    data=output[0] or b''
    if not isinstance(data,bytes) or len(data)>LIMIT:raise WorkspaceOperationError('Workspace operation failed.')
    return data


def invoke(container,action,path,extra=None):
    file_ops.parts(path,root=action=='list')
    if action=='rename':file_ops.parts(extra)
    command=[PYTHON,'-I','-c',SOURCE,action,ROOT,path]
    if extra is not None:command.append(extra)
    try:return checked(container.exec_run(command,user='student',demux=True))
    except (ValueError,FileNotFoundError,FileExistsError,WorkspaceConflictError,WorkspaceOperationError):raise
    except Exception:raise WorkspaceOperationError('Workspace operation failed.') from None


def staged_write(container,path,data,*,exclusive):
    file_ops.parts(path)
    if not isinstance(data,bytes):raise ValueError('Invalid file content.')
    if len(data)>LIMIT:raise WorkspaceLimitError('Maximum file size is 10 MB.')
    token=secrets.token_hex(16);name='wpl-files-'+token;directory='/tmp/'+name
    try:
        encoded=checked(container.exec_run([PYTHON,'-I','-c',STAGE_SCRIPT,name,token],user='root',demux=True))
        identity=json.loads(encoded)
        if not isinstance(identity,list) or len(identity)!=3 or any(type(value) is not int or value<0 for value in identity):
            raise WorkspaceOperationError('Upload staging failed.')
    except Exception:raise WorkspaceOperationError('Upload staging failed.') from None
    error=None
    try:
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            entry=tarfile.TarInfo('payload');entry.size=len(data);entry.mode=0o444;entry.uid=0;entry.gid=0
            tar.addfile(entry,io.BytesIO(data))
        if not container.put_archive(directory,archive.getvalue()):raise WorkspaceOperationError('Upload staging failed.')
        invoke(container,'upload' if exclusive else 'write',path,directory+'/payload')
    except (ValueError,FileNotFoundError,FileExistsError,WorkspaceConflictError,WorkspaceOperationError) as caught:error=caught
    except Exception:error=WorkspaceOperationError('Workspace operation failed.')
    try:checked(container.exec_run([PYTHON,'-I','-c',CLEANUP_SCRIPT,name,token,json.dumps(identity)],user='root',demux=True))
    except Exception:
        if error is None:error=WorkspaceCleanupError('File operation completed, but owned staging cleanup failed. Reload before retrying.')
    if error is not None:raise error from None
