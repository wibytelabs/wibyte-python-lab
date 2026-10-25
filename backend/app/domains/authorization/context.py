"""Server-selected request scope paired with a verified identity.

This is transport-independent context, not an authorization grant. Routes must
verify identity and select their scope before opening a request transaction.
Never construct this from caller-supplied actor, role or capability fields.
"""
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from backend.app.domains.identity.types import VerifiedIdentity


class RequestScope(Enum):
    GLOBAL = 'global'
    PLATFORM = 'platform'
    TENANT = 'tenant'
    PERSONAL = 'personal'


@dataclass(frozen=True)
class RequestContext:
    identity: VerifiedIdentity = field(repr=False)
    scope: RequestScope
    org_id: UUID | None = None

    def __post_init__(self):
        if not isinstance(self.identity, VerifiedIdentity):
            raise ValueError('A verified identity is required.')
        if not isinstance(self.scope, RequestScope):
            raise ValueError('A server-selected request scope is required.')
        if self.org_id is not None and not isinstance(self.org_id, UUID):
            raise ValueError('Organization context must be a UUID.')
        if self.scope is RequestScope.TENANT and self.org_id is None:
            raise ValueError('Tenant scope requires an organization.')
        if self.scope in (RequestScope.GLOBAL, RequestScope.PERSONAL) and self.org_id is not None:
            raise ValueError('This scope cannot carry an organization.')
