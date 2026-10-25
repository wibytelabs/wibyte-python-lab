"""Bounded independent pool; construction never connects or migrates."""
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from backend.app.foundation.settings import FoundationSettings, FoundationConfigurationError
from backend.app.domains.authorization.context import RequestContext

_REQUEST_CONTEXT_SQL = text("""
    SELECT set_config('wpl.actor_id', :actor, true),
           set_config('wpl.scope_kind', :scope, true),
           set_config('wpl.org_id', :org, true),
           set_config('wpl.auth_time', :auth_time, true)
""")

class FoundationDatabase:
    def __init__(self, settings: FoundationSettings):
        if not settings.enabled:
            raise FoundationConfigurationError("Foundation is disabled.")
        self.engine = create_engine(settings.application_database_url,
            pool_size=settings.pool_size, max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout, pool_pre_ping=True, pool_recycle=300,
            hide_parameters=True, connect_args={"connect_timeout": settings.connect_timeout,
                "application_name": "wpl-foundation", "options": (
                    f"-c statement_timeout={settings.statement_timeout_ms} "
                    f"-c lock_timeout={settings.lock_timeout_ms} "
                    f"-c idle_in_transaction_session_timeout={settings.idle_transaction_timeout_ms}")})

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session:
            with session.begin():
                yield session

    @contextmanager
    def request_transaction(self, context: RequestContext):
        """Bind fixed transaction-local settings; the context grants no privileges.

        Callers must keep the yielded session inside this boundary. Existing
        transaction handling rolls back on BaseException, including cancellation.
        Every scope writes every field so absent organization/timing stays empty.
        """
        if not isinstance(context, RequestContext):
            raise ValueError("A typed server request context is required.")
        authenticated_at = context.identity.authenticated_at
        values = {
            "actor": str(context.identity.subject),
            "scope": context.scope.value,
            "org": str(context.org_id) if context.org_id is not None else "",
            "auth_time": str(int(authenticated_at.timestamp())) if authenticated_at is not None else "",
        }
        with self.transaction() as session:
            session.execute(_REQUEST_CONTEXT_SQL, values)
            yield session

    def verify_runtime_role(self):
        with self.transaction() as session:
            unsafe = session.execute(text("""
                SELECT r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole
                    OR r.rolreplication OR n.nspowner = r.oid OR d.datdba = r.oid
                FROM pg_roles r CROSS JOIN pg_namespace n CROSS JOIN pg_database d
                WHERE r.rolname=current_user AND n.nspname='wpl' AND d.datname=current_database()
            """)).scalar_one()
            if unsafe:
                raise FoundationConfigurationError("Foundation runtime role has unsafe privileges.")

    def close(self):
        self.engine.dispose()
