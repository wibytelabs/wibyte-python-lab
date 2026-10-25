"""Transaction-bound idempotency for the implemented tenant mutation services.

Callbacks are trusted server code: no external I/O, transaction commit or caller-
provided callable. Results remain provisional until the caller transaction commits.
Current DB authorization is checked even for cached responses. Future organization
and job operations must explicitly extend operations, scopes and receipt policies.
"""
from dataclasses import dataclass,field
from enum import Enum
import hashlib
import hmac
import json
import re
from uuid import UUID

from sqlalchemy import text

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.authorization.policy import require_tenant_admin
from backend.app.domains.errors import TenantConflict
from backend.app.domains.jobs.payloads import encode_object,InvalidPayload


class TenantOperation(Enum):
    MEMBER_STATUS='set_member_status'
    MEMBER_ROLES='replace_roles'
    COHORT_INSTRUCTORS='set_instructors'


class InvalidIdempotencyInput(ValueError):
    code='invalid_idempotency_input'
    status_code=400
    def __init__(self):super().__init__('Idempotency input or result is invalid.')


@dataclass(frozen=True)
class MutationResult:
    status_code: int
    body: dict=field(repr=False)


@dataclass(frozen=True)
class IdempotencyOutcome:
    result: MutationResult
    replayed: bool


KEY=re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
ROLES={'admin','instructor','student'}
FIELDS={TenantOperation.MEMBER_STATUS:{'membership_id','status','version'},
        TenantOperation.MEMBER_ROLES:{'membership_id','roles','version'},
        TenantOperation.COHORT_INSTRUCTORS:{'cohort_id','version'}}


def checked_result(operation,result):
    if not isinstance(result,MutationResult) or type(result.status_code) is not int or result.status_code!=200:
        raise InvalidIdempotencyInput()
    body=result.body
    if not isinstance(body,dict) or set(body)!=FIELDS[operation]:raise InvalidIdempotencyInput()
    identifier=body.get('cohort_id') if operation is TenantOperation.COHORT_INSTRUCTORS else body.get('membership_id')
    try:
        if not isinstance(identifier,str) or len(identifier)!=36 or UUID(identifier).int==0:raise ValueError
    except (ValueError,TypeError):raise InvalidIdempotencyInput() from None
    if type(body['version']) is not int or not 1<=body['version']<=2147483647:raise InvalidIdempotencyInput()
    if operation is TenantOperation.MEMBER_STATUS and (not isinstance(body['status'],str) or body['status'] not in {'active','suspended','removed'}):
        raise InvalidIdempotencyInput()
    if operation is TenantOperation.MEMBER_ROLES:
        roles=body['roles']
        if (not isinstance(roles,list) or not 1<=len(roles)<=3 or not all(isinstance(role,str) for role in roles)
                or not set(roles)<=ROLES or len(set(roles))!=len(roles)):
            raise InvalidIdempotencyInput()
    return MutationResult(200,json.loads(encode_object(body)))


def execute_idempotent(session,context: RequestContext,operation: TenantOperation,request_key,request_body,callback):
    if (not isinstance(context,RequestContext) or context.scope is not RequestScope.TENANT
            or not isinstance(operation,TenantOperation) or not isinstance(request_key,str)
            or KEY.fullmatch(request_key) is None or not isinstance(request_body,dict) or not callable(callback)
            or not session.in_transaction() or session.in_nested_transaction()):
        raise InvalidIdempotencyInput()
    try:
        request_hash=hashlib.sha256(encode_object({'org_id':str(context.org_id),
            'operation':operation.value,'body':request_body})).hexdigest()
    except InvalidPayload:raise InvalidIdempotencyInput() from None
    require_tenant_admin(session,context.identity,context.org_id)
    key_tuple=[str(context.identity.subject),operation.value,'tenant',str(context.org_id),request_key]
    lock_key=int.from_bytes(hashlib.blake2b(json.dumps(key_tuple,separators=(',',':')).encode(),digest_size=8).digest(),signed=True)
    parameters={'actor':context.identity.subject,'operation':operation.value,'org':context.org_id,
                'request_key':request_key,'request_hash':request_hash}
    # The savepoint also rolls back callback writes if a caller catches the error
    # while retaining the outer transaction. The PK remains the final uniqueness guard.
    with session.begin_nested():
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':lock_key})
        require_tenant_admin(session,context.identity,context.org_id)
        row=session.execute(text('''SELECT request_hash,response_status,response FROM wpl.idempotency_records
            WHERE actor_id=:actor AND operation=:operation AND scope_kind='tenant'
              AND scope_id=:org AND org_id=:org AND request_key=:request_key'''),parameters).mappings().one_or_none()
        if row is not None:
            if not hmac.compare_digest(row['request_hash'],request_hash):
                raise TenantConflict('idempotency_conflict','This request key was already used for different input.')
            return IdempotencyOutcome(checked_result(operation,MutationResult(row['response_status'],row['response'])),True)
        result=checked_result(operation,callback(session))
        parameters.update({'status':result.status_code,'response':encode_object(result.body).decode('utf-8')})
        session.execute(text('''INSERT INTO wpl.idempotency_records(actor_id,operation,scope_kind,scope_id,org_id,
            request_key,request_hash,response_status,response)
            VALUES (:actor,:operation,'tenant',:org,:org,:request_key,:request_hash,:status,CAST(:response AS jsonb))'''),parameters)
        return IdempotencyOutcome(result,False)
