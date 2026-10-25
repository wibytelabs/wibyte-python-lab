"""Explicit executive organization reads; no tenant impersonation or grants."""
from uuid import UUID
from sqlalchemy import text
from backend.app.domains.errors import AuthorizationDenied
from backend.app.domains.identity.types import VerifiedIdentity


def require_organization_directory(session,identity: VerifiedIdentity,org_id: UUID | None=None):
    if not isinstance(identity,VerifiedIdentity) or (org_id is not None and not isinstance(org_id,UUID)):
        raise AuthorizationDenied()
    bound=session.execute(text("""SELECT current_user,current_setting('wpl.actor_id',true),
        current_setting('wpl.scope_kind',true),current_setting('wpl.org_id',true)""")).one()
    if tuple(bound)!=('wpl_app',str(identity.subject),'platform',str(org_id) if org_id is not None else ''):
        raise AuthorizationDenied()
    permitted=session.execute(text("""SELECT EXISTS(SELECT 1 FROM wpl.platform_roles
        WHERE user_id=:actor AND capability='orgs' AND (expires_at IS NULL OR expires_at>statement_timestamp()))"""),
        {'actor':identity.subject}).scalar_one()
    # RLS on platform_roles also requires the current stored user to be active.
    if not permitted:raise AuthorizationDenied()
