"""Minimal instructor mutation service; full cohort product remains P05."""
from uuid import UUID
from sqlalchemy import text
from backend.app.domains.errors import TenantConflict
from backend.app.domains.organizations.service import authorized_org, expected_version, reason_text, audit


def set_instructors(session, identity, org_id: UUID, cohort_id: UUID, members,
                    version: int, reason: str):
    reason=reason_text(reason)
    if not isinstance(members,(list,tuple,set,frozenset)) or len(members)>100 or any(not isinstance(value,UUID) for value in members):
        raise TenantConflict('invalid_instructors','Select at most 100 same-organization instructors.')
    members=set(members)
    authorized_org(session,identity,org_id)
    cohort=session.execute(text('SELECT id,status,version FROM wpl.cohorts WHERE org_id=:org AND id=:cohort FOR UPDATE'),
                           {'org':org_id,'cohort':cohort_id}).mappings().one_or_none()
    if cohort is None:
        raise TenantConflict('cohort_missing','The selected cohort is unavailable.')
    expected_version(cohort['version'],version)
    if cohort['status']=='active' and not members:
        raise TenantConflict('last_instructor','An active cohort needs at least one active instructor.')
    for member in sorted(members):
        eligible=session.execute(text('''SELECT EXISTS(SELECT 1 FROM wpl.organization_memberships m
            JOIN wpl.users u ON u.id=m.user_id
            JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='instructor'
            WHERE m.org_id=:org AND m.id=:member AND m.status='active' AND u.global_state='active')'''),
            {'org':org_id,'member':member}).scalar_one()
        if not eligible:
            raise TenantConflict('instructor_ineligible','Every instructor must be an active instructor in this organization.')
    old=set(session.execute(text("SELECT membership_id FROM wpl.cohort_memberships WHERE org_id=:org AND cohort_id=:cohort AND role='instructor' AND status='active'"),
                            {'org':org_id,'cohort':cohort_id}).scalars())
    # Add replacements first so immediate constraints also retain staffing.
    for member in sorted(members-old):
        session.execute(text("""INSERT INTO wpl.cohort_memberships(org_id,cohort_id,membership_id,role,status)
            VALUES (:org,:cohort,:member,'instructor','active') ON CONFLICT (org_id,cohort_id,membership_id,role)
            DO UPDATE SET status='active'"""),{'org':org_id,'cohort':cohort_id,'member':member})
    for member in sorted(old-members):
        session.execute(text("UPDATE wpl.cohort_memberships SET status='removed' WHERE org_id=:org AND cohort_id=:cohort AND membership_id=:member AND role='instructor'"),
                        {'org':org_id,'cohort':cohort_id,'member':member})
    if old != members:
        audit(session,identity,org_id,'cohort_instructors_changed',reason,'cohort',cohort_id,
              {'from':[str(value) for value in sorted(old)],'to':[str(value) for value in sorted(members)]})
    return dict(session.execute(text('SELECT id,version FROM wpl.cohorts WHERE org_id=:org AND id=:cohort'),
                                {'org':org_id,'cohort':cohort_id}).mappings().one())
