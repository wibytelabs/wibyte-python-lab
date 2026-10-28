"""Stdlib-only descriptor-relative workspace operations, supplied to a container as source.

Root is selected by the trusted adapter, never by a request path. This module does
not import application configuration, Docker or providers and does no work on import.
"""
import ctypes
import errno
import json
import os
import secrets
import stat
import sys

LIMIT=10*1024*1024
MAX_ENTRIES=4096
MAX_DEPTH=32
MAX_TREE_BYTES=64*1024*1024
DIRECTORY=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
REGULAR=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC

class FileOperationError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__({10:'Invalid or protected workspace path.',11:'Destination already exists.',12:'Workspace path not found.',
            13:'Workspace file or traversal limit exceeded.',14:'Workspace changed; reload before retrying.',15:'Workspace operation failed.'}[code])


def fail(code):raise FileOperationError(code)

def parts(path,*,root=False):
    if not isinstance(path,str):fail(10)
    if root and path=='.':return ()
    try:encoded=path.encode('utf-8')
    except UnicodeError:fail(10)
    values=path.split('/')
    if (not path or path.startswith('/') or len(encoded)>4096 or len(values)>MAX_DEPTH or '\\' in path
            or any(ord(char)<32 or ord(char)==127 for char in path)
            or any(value in ('','.','..','.git') or len(value.encode('utf-8'))>255 for value in values)):
        fail(10)
    return tuple(values)


def identity(info):return info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)

def regular(info):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:fail(10)
    if info.st_size>LIMIT:fail(13)


def unchanged(parent,name,expected):
    current=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if identity(current)!=identity(expected):fail(14)
    if stat.S_ISREG(current.st_mode):regular(current)
    return current


def no_replace(source_parent,source,destination_parent,destination):
    # Linux atomic no-overwrite rename: fail closed if libc/kernel lacks it.
    # A check-then-os.rename fallback could overwrite a concurrently created file.
    library=ctypes.CDLL(None,use_errno=True)
    function=getattr(library,'renameat2',None)
    if function is None:fail(15)
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    function.restype=ctypes.c_int
    if function(source_parent,os.fsencode(source),destination_parent,os.fsencode(destination),1):
        number=ctypes.get_errno()
        raise OSError(number,os.strerror(number))


class Workspace:
    def __init__(self,root):
        if not isinstance(root,str) or not root.startswith('/') or any(value in ('.','..') for value in root.split('/')):fail(10)
        descriptor=os.open('/',DIRECTORY)
        try:
            for value in filter(None,root.split('/')):
                next_fd=os.open(value,DIRECTORY,dir_fd=descriptor)
                os.close(descriptor);descriptor=next_fd
            self.root=descriptor
        except BaseException:
            os.close(descriptor);raise

    def __enter__(self):return self
    def __exit__(self,*_error):os.close(self.root)

    def directory(self,values,*,create=False):
        descriptor=os.dup(self.root)
        try:
            for value in values:
                if create:
                    try:os.mkdir(value,0o755,dir_fd=descriptor)
                    except FileExistsError:pass
                next_fd=os.open(value,DIRECTORY,dir_fd=descriptor)
                os.close(descriptor);descriptor=next_fd
            return descriptor
        except BaseException:
            os.close(descriptor);raise

    def read(self,path):
        values=parts(path);parent=self.directory(values[:-1]);descriptor=None
        try:
            descriptor=os.open(values[-1],REGULAR,dir_fd=parent)
            before=os.fstat(descriptor);regular(before)
            result=bytearray()
            while True:
                chunk=os.read(descriptor,min(65536,LIMIT+1-len(result)))
                if not chunk:break
                result.extend(chunk)
                if len(result)>LIMIT:fail(13)
            after=os.fstat(descriptor);regular(after)
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):fail(14)
            return bytes(result)
        finally:
            if descriptor is not None:os.close(descriptor)
            os.close(parent)

    def write(self,path,data,*,exclusive=False):
        values=parts(path)
        if not isinstance(data,bytes):fail(10)
        if len(data)>LIMIT:fail(13)
        parent=self.directory(values[:-1],create=True);descriptor=None;temporary=None;owned=None
        try:
            try:before=os.stat(values[-1],dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:before=None
            if before is not None:
                regular(before)
                if exclusive:fail(11)
            temporary='.wpl-edit-'+secrets.token_hex(16)
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
            owned=os.fstat(descriptor)
            remaining=memoryview(data)
            while remaining:
                written=os.write(descriptor,remaining)
                if written<=0:fail(15)
                remaining=remaining[written:]
            os.fchmod(descriptor,stat.S_IMODE(before.st_mode)&0o777 if before else 0o644)
            os.fsync(descriptor)
            # Validate names again; a parent descriptor never follows a swapped link.
            unchanged(parent,temporary,owned)
            if before is not None:unchanged(parent,values[-1],before)
            else:
                try:os.stat(values[-1],dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:pass
                else:fail(11)
            if exclusive or before is None:no_replace(parent,temporary,parent,values[-1])
            else:os.replace(temporary,values[-1],src_dir_fd=parent,dst_dir_fd=parent)
            # Atomic rename is the commit point. No later durability operation
            # may report this committed update as a pre-commit failure.
            temporary=None
        finally:
            if temporary is not None and owned is not None:
                # Never remove a different inode that replaced this operation's temp.
                try:
                    current=os.stat(temporary,dir_fd=parent,follow_symlinks=False)
                    if identity(current)==identity(owned):os.unlink(temporary,dir_fd=parent)
                except FileNotFoundError:pass
            if descriptor is not None:os.close(descriptor)
            os.close(parent)

    def mkdir(self,path):
        descriptor=self.directory(parts(path),create=True)
        os.close(descriptor)

    def list(self,path='.'):
        descriptor=self.directory(parts(path,root=True));result=[]
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    if entry.name=='.git':continue
                    parts(entry.name)
                    if len(result)>=MAX_ENTRIES:fail(13)
                    info=os.stat(entry.name,dir_fd=descriptor,follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):regular(info);kind='file'
                    elif stat.S_ISDIR(info.st_mode):kind='directory'
                    else:fail(10)
                    result.append({'name':entry.name,'type':kind})
            return sorted(result,key=lambda item:item['name'])
        finally:os.close(descriptor)

    def walk(self,values):
        plan=[];total=[0]
        def visit(parent,name,prefix,depth):
            if depth>MAX_DEPTH or len(plan)>=MAX_ENTRIES:fail(13)
            parts(name)
            info=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                regular(info);total[0]+=info.st_size
                if total[0]>MAX_TREE_BYTES:fail(13)
            elif stat.S_ISDIR(info.st_mode):
                descriptor=os.open(name,DIRECTORY,dir_fd=parent)
                try:
                    if identity(os.fstat(descriptor))!=identity(info):fail(14)
                    with os.scandir(descriptor) as entries:
                        names=[]
                        for entry in entries:
                            names.append(entry.name)
                            if len(names)>MAX_ENTRIES:fail(13)
                    # Preflight all descendants before any destructive action.
                    plan.append((prefix+(name,),info))
                    for child in sorted(names):visit(descriptor,child,prefix+(name,),depth+1)
                    return
                finally:os.close(descriptor)
            else:fail(10)
            plan.append((prefix+(name,),info))
        parent=self.directory(values[:-1])
        try:visit(parent,values[-1],values[:-1],1)
        finally:os.close(parent)
        return plan

    def rename(self,old,new):
        source=parts(old);destination=parts(new)
        if source==destination or destination[:len(source)]==source:fail(10)
        plan=self.walk(source)
        source_parent=self.directory(source[:-1]);destination_parent=None
        try:
            destination_parent=self.directory(destination[:-1],create=True)
            unchanged(source_parent,source[-1],plan[0][1])
            no_replace(source_parent,source[-1],destination_parent,destination[-1])
        finally:
            if destination_parent is not None:os.close(destination_parent)
            os.close(source_parent)

    def delete(self,path):
        values=parts(path);plan=self.walk(values)
        for relative,expected in reversed(plan):
            parent=self.directory(relative[:-1])
            try:
                unchanged(parent,relative[-1],expected)
                if stat.S_ISDIR(expected.st_mode):os.rmdir(relative[-1],dir_fd=parent)
                else:os.unlink(relative[-1],dir_fd=parent)
            finally:os.close(parent)


def main(argv=None):
    values=sys.argv[1:] if argv is None else argv
    try:
        if len(values)<3:fail(10)
        action,root,path=values[:3]
        if action not in ('list','read','download','write','upload','create','mkdir','delete','rename'):fail(10)
        with Workspace(root) as workspace:
            if action in ('write','upload'):
                if len(values)!=4:fail(10)
                # Trusted adapter supplies its owned staged regular payload path.
                descriptor=os.open(values[3],REGULAR)
                try:
                    regular(os.fstat(descriptor));data=bytearray()
                    while True:
                        chunk=os.read(descriptor,min(65536,LIMIT+1-len(data)))
                        if not chunk:break
                        data.extend(chunk)
                        if len(data)>LIMIT:fail(13)
                finally:os.close(descriptor)
                workspace.write(path,bytes(data),exclusive=action=='upload')
            elif action=='rename':
                if len(values)!=4:fail(10)
                workspace.rename(path,values[3])
            elif len(values)!=3:fail(10)
            elif action in ('read','download'):sys.stdout.buffer.write(workspace.read(path))
            elif action=='list':print(json.dumps(workspace.list(path),ensure_ascii=True))
            elif action=='create':workspace.write(path,b'',exclusive=True)
            elif action=='mkdir':workspace.mkdir(path)
            elif action=='delete':workspace.delete(path)
        return 0
    except FileOperationError as error:return error.code
    except OSError as error:
        return {errno.ENOENT:12,errno.EEXIST:11,errno.ENOTEMPTY:11,errno.ELOOP:10,errno.ENOTDIR:10,
            errno.EISDIR:10,errno.EACCES:10,errno.EPERM:10,errno.EINVAL:10,errno.EXDEV:10,errno.ENAMETOOLONG:10}.get(error.errno,15)
    except (ValueError,UnicodeError):return 10


if __name__=='__main__':raise SystemExit(main())
