"""Transaction-bound tenant mutations. Callers own commit/rollback.

No HTTP endpoints or synthetic-identity switches are exposed here. Services use
verified server identity and recheck actual grants after locking the parent.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
from uuid import UUID, uuid4
from sqlalchemy import text
from backend.app.domains.authorization.policy import require_tenant_admin
from backend.app.domains.errors import TenantConflict
from backend.app.domains.identity.types import VerifiedIdentity


def utcnow():
    return datetime.now(timezone.utc)


def reason_text(reason):
    if not isinstance(reason,str) or not 5 <= len(reason.strip()) <= 1000:
        raise TenantConflict('invalid_reason','A reason of 5–1000 characters is required.')
    return reason.strip()


def authorized_org(session, identity, org_id, *, primary=False):
    require_tenant_admin(session,identity,org_id,primary=primary)
    row=session.execute(text('SELECT id,primary_admin_membership_id,version FROM wpl.organizations WHERE id=:org FOR UPDATE'), {'org':org_id}).mappings().one()
    require_tenant_admin(session,identity,org_id,primary=primary)
    return row


def expected_version(actual, expected):
    if type(expected) is not int or expected < 1 or actual != expected:
        raise TenantConflict('version_conflict','The record changed; reload before retrying.')


def audit(session, identity, org_id, action, reason, target_type, target_id, changes):
    import json
    session.execute(text('''INSERT INTO wpl.audit_events(id,actor_id,org_id,action,reason,target_type,target_id,changes)
        VALUES (:id,:actor,:org,:action,:reason,:kind,:target,CAST(:changes AS jsonb))'''),
        {'id':uuid4(),'actor':identity.subject,'org':org_id,'action':action,'reason':reason,
         'kind':target_type,'target':target_id,'changes':json.dumps(changes)})


def member_row(session, org_id, member_id):
    row=session.execute(text('SELECT id,user_id,status,version FROM wpl.organization_memberships WHERE org_id=:org AND id=:member FOR UPDATE'),
                        {'org':org_id,'member':member_id}).mappings().one_or_none()
    if row is None:
        raise TenantConflict('member_missing','The selected membership is unavailable.')
    return row


def protect_final_instructor(session, org_id, member_id):
    # Lock affected cohorts in stable order before evaluating current staffing.
    session.execute(text('''SELECT c.id FROM wpl.cohorts c WHERE c.org_id=:org AND EXISTS (
        SELECT 1 FROM wpl.cohort_memberships cm WHERE cm.org_id=c.org_id AND cm.cohort_id=c.id
        AND cm.membership_id=:member) ORDER BY c.id FOR UPDATE'''), {'org':org_id,'member':member_id}).all()
    stranded=session.execute(text('''SELECT EXISTS(SELECT 1 FROM wpl.cohorts c
        JOIN wpl.cohort_memberships own ON own.org_id=c.org_id AND own.cohort_id=c.id
        WHERE c.org_id=:org AND c.status='active' AND own.membership_id=:member
          AND own.role='instructor' AND own.status='active' AND NOT EXISTS (
            SELECT 1 FROM wpl.cohort_memberships cm
            JOIN wpl.organization_memberships m ON m.org_id=cm.org_id AND m.id=cm.membership_id
            JOIN wpl.users u ON u.id=m.user_id
            JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='instructor'
            WHERE cm.org_id=c.org_id AND cm.cohort_id=c.id AND cm.membership_id<>:member
              AND cm.role='instructor' AND cm.status='active' AND m.status='active' AND u.global_state='active'))'''),
        {'org':org_id,'member':member_id}).scalar_one()
    if stranded:
        raise TenantConflict('last_instructor','Assign another active instructor before this change.')


def set_member_status(session, identity: VerifiedIdentity, org_id: UUID, member_id: UUID,
                      status: str, version: int, reason: str):
    reason=reason_text(reason)
    if status not in {'active','suspended','removed'}:
        raise TenantConflict('invalid_status','Unsupported membership status.')
    org=authorized_org(session,identity,org_id)
    member=member_row(session,org_id,member_id)
    expected_version(member['version'],version)
    if member_id == org['primary_admin_membership_id'] and status != 'active':
        raise TenantConflict('protected_primary','Transfer the designated primary before this change.')
    if member['status'] in {'invite_pending','removed'}:
        raise TenantConflict('invalid_transition','Invitation binding or rejoining requires its explicit workflow.')
    if status == member['status']:
        return dict(member)
    if status != 'active':
        protect_final_instructor(session,org_id,member_id)
    session.execute(text('UPDATE wpl.organization_memberships SET status=:status WHERE org_id=:org AND id=:member'),
                    {'status':status,'org':org_id,'member':member_id})
    audit(session,identity,org_id,'membership_status_changed',reason,'membership',member_id,{'from':member['status'],'to':status})
    return dict(member_row(session,org_id,member_id))


def replace_roles(session, identity: VerifiedIdentity, org_id: UUID, member_id: UUID,
                  roles, version: int, reason: str):
    reason=reason_text(reason)
    if not isinstance(roles,(list,tuple,set,frozenset)) or not 1 <= len(roles) <= 3 or not all(isinstance(role,str) for role in roles) or not set(roles) <= {'admin','instructor','student'}:
        raise TenantConflict('invalid_roles','Select only supported organization roles.')
    roles=set(roles)
    org=authorized_org(session,identity,org_id)
    member=member_row(session,org_id,member_id)
    expected_version(member['version'],version)
    if member_id == org['primary_admin_membership_id'] and 'admin' not in roles:
        raise TenantConflict('protected_primary','The designated primary must retain admin authority.')
    old=set(session.execute(text('SELECT role FROM wpl.organization_roles WHERE org_id=:org AND membership_id=:member'),
                            {'org':org_id,'member':member_id}).scalars())
    if 'instructor' in old - roles:
        protect_final_instructor(session,org_id,member_id)
    for role in sorted(roles-old):
        session.execute(text('INSERT INTO wpl.organization_roles(org_id,membership_id,role) VALUES (:org,:member,:role)'),{'org':org_id,'member':member_id,'role':role})
    for role in sorted(old-roles):
        session.execute(text('DELETE FROM wpl.organization_roles WHERE org_id=:org AND membership_id=:member AND role=:role'),{'org':org_id,'member':member_id,'role':role})
    if old != roles:
        # Role rows have no individual version; advance the membership receipt too.
        session.execute(text('UPDATE wpl.organization_memberships SET version=version+1 WHERE org_id=:org AND id=:member'),{'org':org_id,'member':member_id})
        audit(session,identity,org_id,'membership_roles_changed',reason,'membership',member_id,{'from':sorted(old),'to':sorted(roles)})
    return {'membership_id':member_id,'roles':sorted(roles),'version':member_row(session,org_id,member_id)['version']}


def complete_primary_transfer(session, identity: VerifiedIdentity, org_id: UUID, transfer_id: UUID,
                              confirmation: str, version: int, *, clock=utcnow):
    # Preview creation/HTTP confirmation and notification outbox are added in P02.5/P02.4.
    org=authorized_org(session,identity,org_id,primary=True)
    now=clock()
    authenticated=identity.authenticated_at
    if authenticated is None or not timedelta(seconds=-30) <= now-authenticated <= timedelta(minutes=5):
        raise TenantConflict('recent_auth_required','Authenticate again before transferring the primary designation.')
    expected_version(org['version'],version)
    row=session.execute(text('SELECT * FROM wpl.primary_admin_transfers WHERE org_id=:org AND id=:transfer FOR UPDATE'),
                        {'org':org_id,'transfer':transfer_id}).mappings().one_or_none()
    if (row is None or row['status']!='preview' or row['actor_id']!=identity.subject or row['expires_at']<=now
            or row['expected_version']!=version or row['from_membership_id']!=org['primary_admin_membership_id']):
        raise TenantConflict('invalid_confirmation','The transfer preview is stale or unavailable.')
    if not isinstance(confirmation,str) or not 1 <= len(confirmation) <= 256 or not hmac.compare_digest(
            bytes(row['confirmation_hash']),hashlib.sha256(confirmation.encode()).digest()):
        raise TenantConflict('invalid_confirmation','The transfer confirmation does not match.')
    eligible=session.execute(text('''SELECT EXISTS(SELECT 1 FROM wpl.organization_memberships m
        JOIN wpl.users u ON u.id=m.user_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='admin'
        WHERE m.org_id=:org AND m.id=:target AND m.status='active' AND u.global_state='active')'''),
        {'org':org_id,'target':row['to_membership_id']}).scalar_one()
    if not eligible:
        raise TenantConflict('target_ineligible','Choose an active administrator in this organization.')
    session.execute(text('UPDATE wpl.organizations SET primary_admin_membership_id=:target WHERE id=:org'),
                    {'org':org_id,'target':row['to_membership_id']})
    session.execute(text("UPDATE wpl.primary_admin_transfers SET status='completed',completed_at=:now WHERE id=:id"),{'now':now,'id':transfer_id})
    audit(session,identity,org_id,'primary_transferred','Confirmed primary transfer','organization',org_id,
          {'from_membership_id':str(row['from_membership_id']),'to_membership_id':str(row['to_membership_id'])})
    return dict(session.execute(text('SELECT id,primary_admin_membership_id,version FROM wpl.organizations WHERE id=:org'),{'org':org_id}).mappings().one())
