"""Verified identity contains no authorization grants.

Only server verification dependencies construct this in production. Synthetic
identities are constructed directly by fixture tests; no runtime bypass exists.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

@dataclass(frozen=True)
class VerifiedIdentity:
    subject: UUID
    authenticated_at: datetime | None = None
    verified_email: str | None = None
    session_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.subject, UUID):
            raise ValueError('Verified subject must be a UUID.')
        if self.authenticated_at is not None and (
            self.authenticated_at.tzinfo is None or self.authenticated_at.utcoffset() is None
        ):
            raise ValueError('Authentication time must be timezone-aware.')
