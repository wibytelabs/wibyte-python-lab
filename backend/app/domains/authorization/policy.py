"""Initial shared mutation policy. Current DB grants, never identity metadata."""
from uuid import UUID
from sqlalchemy import text
from backend.app.domains.errors import AuthorizationDenied
from backend.app.domains.identity.types import VerifiedIdentity


def require_tenant_admin(session, identity: VerifiedIdentity, org_id: UUID, *, primary=False):
    if not isinstance(identity, VerifiedIdentity) or not isinstance(org_id, UUID):
        raise AuthorizationDenied()
    bound=session.execute(text("""SELECT current_user,current_setting('wpl.actor_id',true),
        current_setting('wpl.scope_kind',true),current_setting('wpl.org_id',true)""")).one()
    # The migration owner is a trusted fixture/maintenance identity, never web runtime.
    # Application and future worker callers must not substitute another identity or org.
    if bound[0]!='wpl_migrator' and tuple(bound)!=('wpl_app',str(identity.subject),'tenant',str(org_id)):
        raise AuthorizationDenied()
    member = session.execute(text("""
        SELECT m.id, o.primary_admin_membership_id
        FROM wpl.users u JOIN wpl.organization_memberships m ON m.user_id=u.id
        JOIN wpl.organizations o ON o.id=m.org_id
        JOIN wpl.organization_roles r ON r.org_id=m.org_id AND r.membership_id=m.id AND r.role='admin'
        WHERE u.id=:actor AND u.global_state='active' AND m.org_id=:org
          AND m.status='active' AND o.status='active'
    """), {'actor': identity.subject, 'org': org_id}).mappings().one_or_none()
    if member is None or (primary and member['id'] != member['primary_admin_membership_id']):
        raise AuthorizationDenied()
    return member['id']
