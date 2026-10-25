"""Real-runtime-role pool reuse across transaction and cancellation boundaries.

These prove context lifetime, not tenant authorization: scoped RLS follows in
its own slice. No private settings, provider calls or legacy database access.
"""
import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import os
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext, RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings, postgres_url


SETTINGS = text("""SELECT pg_backend_pid(),current_user,
    current_setting('wpl.actor_id',true),current_setting('wpl.scope_kind',true),
    current_setting('wpl.org_id',true),current_setting('wpl.auth_time',true)""")


class ContextShapeTests(unittest.TestCase):
    def test_context_rejects_untyped_actor_scope_and_invalid_scope_org_combinations(self):
        identity = VerifiedIdentity(uuid4())
        for args in (
            (str(identity.subject), RequestScope.GLOBAL, None),
            (identity, 'tenant', uuid4()),
            (identity, RequestScope.TENANT, None),
            (identity, RequestScope.TENANT, 'caller-org'),
            (identity, RequestScope.GLOBAL, uuid4()),
            (identity, RequestScope.PERSONAL, uuid4()),
        ):
            with self.subTest(scope=args[1]), self.assertRaises(ValueError):
                RequestContext(*args)
        context = RequestContext(identity, RequestScope.PLATFORM, uuid4())
        with self.assertRaises(FrozenInstanceError):
            context.org_id = uuid4()


class ContextPoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'], 'fixture')
        if url.host != 'fixture-db' or url.database != 'wpl_fixture':
            raise RuntimeError('Refusing non-fixture database target.')
        cls.database = FoundationDatabase(FoundationSettings(
            enabled=True, application_database_url=url, pool_size=1,
            max_overflow=0))

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def setUp(self):
        self.first = RequestContext(VerifiedIdentity(uuid4(), datetime.now(timezone.utc)),
                                    RequestScope.TENANT, uuid4())
        self.second = RequestContext(VerifiedIdentity(uuid4()), RequestScope.TENANT, uuid4())

    def bound_row(self, session, context):
        row = session.execute(SETTINGS).one()
        expected_time = (str(int(context.identity.authenticated_at.timestamp()))
                         if context.identity.authenticated_at is not None else '')
        self.assertEqual(tuple(row[1:]), ('wpl_app', str(context.identity.subject),
                         context.scope.value, str(context.org_id) if context.org_id else '', expected_time))
        return row[0]

    def assert_reused_and_cleared(self, previous_pid):
        self.assertEqual(self.database.engine.pool.checkedout(), 0)
        with self.database.transaction() as session:
            row = session.execute(SETTINGS).one()
            self.assertEqual(row[0], previous_pid, 'Expected reuse of the same PostgreSQL connection')
            self.assertEqual(row[1], 'wpl_app')
            self.assertTrue(all(value in (None, '') for value in row[2:]))
        with self.database.request_transaction(self.second) as session:
            self.assertEqual(self.bound_row(session, self.second), previous_pid)
        self.assertEqual(self.database.engine.pool.checkedout(), 0)

    def test_commit_reuses_connection_without_previous_actor_org_or_auth_time(self):
        with self.database.request_transaction(self.first) as session:
            pid = self.bound_row(session, self.first)
        self.assert_reused_and_cleared(pid)
        print('Actual wpl_app pool size 1: same backend PID reused; actor/org/auth timing cleared.', flush=True)

    def test_python_exception_rolls_back_and_clears_context(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic request failure'):
            with self.database.request_transaction(self.first) as session:
                pid = self.bound_row(session, self.first)
                raise RuntimeError('synthetic request failure')
        self.assert_reused_and_cleared(pid)

    def test_database_error_rolls_back_and_clears_context(self):
        with self.assertRaises(DBAPIError):
            with self.database.request_transaction(self.first) as session:
                pid = self.bound_row(session, self.first)
                session.execute(text('SELECT 1/0'))
        self.assert_reused_and_cleared(pid)

    def test_request_cancellation_rolls_back_and_clears_context(self):
        # CancelledError is a BaseException, not an ordinary Exception.
        with self.assertRaises(asyncio.CancelledError):
            with self.database.request_transaction(self.first) as session:
                pid = self.bound_row(session, self.first)
                raise asyncio.CancelledError()
        self.assert_reused_and_cleared(pid)

    def test_actual_statement_cancellation_rolls_back_and_clears_context(self):
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(self.first) as session:
                pid = self.bound_row(session, self.first)
                session.execute(text("SELECT set_config('statement_timeout','100ms',true)"))
                session.execute(text('SELECT pg_sleep(1)'))
        self.assertEqual(result.exception.orig.sqlstate, '57014')
        self.assert_reused_and_cleared(pid)

    def test_scope_changes_overwrite_all_context_fields(self):
        with self.database.request_transaction(self.first) as session:
            pid = self.bound_row(session, self.first)
        for scope, org in ((RequestScope.PLATFORM, uuid4()), (RequestScope.PLATFORM, None),
                           (RequestScope.PERSONAL, None), (RequestScope.GLOBAL, None)):
            context = RequestContext(self.second.identity, scope, org)
            with self.subTest(scope=scope, targeted=org is not None):
                with self.database.request_transaction(context) as session:
                    self.assertEqual(self.bound_row(session, context), pid)
        self.assert_reused_and_cleared(pid)

    def test_untyped_context_is_rejected_before_checkout(self):
        with self.assertRaises(ValueError):
            with self.database.request_transaction({'actor_id': uuid4(), 'scope_kind': 'tenant'}):
                self.fail('An untyped caller context was accepted')
        self.assertEqual(self.database.engine.pool.checkedout(), 0)
