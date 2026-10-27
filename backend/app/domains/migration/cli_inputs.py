"""Private local fixture inputs, only read when explicit import is requested."""
import json
import os
import re
from pathlib import Path
import stat
from uuid import UUID
from backend.app.domains.jobs.payloads import unique_object
from backend.app.domains.migration.importer import RehearsalError


def private_bytes(path,limit):
    if not isinstance(path,Path) or not path.is_absolute():raise RehearsalError('explicit_private_input_required')
    descriptor=None
    try:
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077 or not 1<=info.st_size<=limit:
            raise RehearsalError('private_input_permissions_or_size_invalid')
        data=b''
        while len(data)<=limit:
            value=os.read(descriptor,limit+1-len(data))
            if not value:break
            data+=value
        after=os.fstat(descriptor)
        if len(data)>limit or (info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise RehearsalError('private_input_permissions_or_size_invalid')
        return data
    except OSError:raise RehearsalError('private_input_unavailable') from None
    finally:
        if descriptor is not None:os.close(descriptor)


def read_bindings(path):
    try:
        value=json.loads(private_bytes(path,65536).decode('utf-8'),object_pairs_hook=unique_object)
        if not isinstance(value,dict) or len(value)>10000:raise ValueError
        result={UUID(key):UUID(target) for key,target in value.items()}
        if any(str(UUID(key))!=key or str(UUID(target))!=target for key,target in value.items()):raise ValueError
        return result
    except (ValueError,TypeError,AttributeError,UnicodeError,RecursionError):raise RehearsalError('invalid_explicit_identity_mapping') from None


class FileKeys:
    def __init__(self,path,reference):
        if not isinstance(reference,str) or re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}',reference) is None:
            raise RehearsalError('invalid_key_reference')
        self._value=private_bytes(path,32)
        if len(self._value)!=32:raise RehearsalError('invalid_private_key_length')
        self._reference=reference
    def current_reference(self):return self._reference
    def resolve(self,reference):
        if reference!=self._reference:raise KeyError
        return self._value
