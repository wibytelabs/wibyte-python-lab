"""Synthetic-key crypto and explicit ciphertext persistence; no real delivery."""
from dataclasses import replace
import os
import unittest
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.domains.authorization.context import RequestContext,RequestScope
from backend.app.domains.identity.types import VerifiedIdentity
from backend.app.domains.jobs.payloads import (
    PayloadCipher,PayloadBinding,PayloadScope,EncryptedPayload,InvalidPayload,
    PayloadKeyUnavailable,MAX_CLEARTEXT_BYTES,MAX_CIPHERTEXT_BYTES,MAGIC,ZERO,aad,
)
from backend.app.foundation.db import FoundationDatabase
from backend.app.foundation.settings import FoundationSettings,postgres_url
from backend.app.foundation.migrate import migrate
from test_schema import connect,seed_org

MARKER='synthetic-activation-capability-never-log'


class SyntheticKeys:
    def __init__(self):
        self.active='fixture/key-v1'
        self.keys={self.active:AESGCM.generate_key(bit_length=256)}
    def current_reference(self):return self.active
    def resolve(self,reference):return self.keys[reference]


def binding(scope=PayloadScope.TENANT):
    actor=uuid4()
    scope_id=actor if scope is PayloadScope.PERSONAL else ZERO if scope is PayloadScope.PLATFORM else uuid4()
    return PayloadBinding(scope,scope_id,actor,uuid4(),uuid4(),'deliver_invitation')


class PayloadCryptoTests(unittest.TestCase):
    def setUp(self):
        self.keys=SyntheticKeys()
        self.cipher=PayloadCipher(self.keys)
        self.bound=binding()
        self.value={'activation_token':MARKER,'email':'synthetic@example.invalid','nested':{'valid':True,'roles':['admin']}}

    def test_real_aes256_round_trip_each_scope_random_nonce_and_redacted_envelope(self):
        for scope in PayloadScope:
            bound=binding(scope)
            one=self.cipher.encrypt(self.value,bound)
            two=self.cipher.encrypt(self.value,bound)
            self.assertEqual(self.cipher.decrypt(one,bound),self.value)
            self.assertNotEqual(one.ciphertext,two.ciphertext)
            self.assertNotIn(MARKER.encode(),one.ciphertext)
            self.assertNotIn('synthetic@example.invalid'.encode(),one.ciphertext)
            self.assertNotIn(MARKER,repr(one))
            self.assertNotIn(repr(one.ciphertext),repr(one))

    def test_all_binding_dimensions_prevent_payload_replay_or_cross_scope_swap(self):
        envelope=self.cipher.encrypt(self.value,self.bound)
        cases=(replace(self.bound,scope_id=uuid4()),replace(self.bound,actor_id=uuid4()),
               replace(self.bound,operation_id=uuid4()),replace(self.bound,payload_id=uuid4()),
               replace(self.bound,purpose='other_operation'),replace(self.bound,scope=PayloadScope.PLATFORM,scope_id=ZERO))
        for other in cases:
            with self.subTest(scope=other.scope),self.assertRaises(InvalidPayload) as result:
                self.cipher.decrypt(envelope,other)
            self.assertNotIn(MARKER,str(result.exception))
        # Even an alias resolving to identical key bytes is bound to the reference.
        self.keys.keys['fixture/key-alias']=self.keys.keys[self.keys.active]
        with self.assertRaises(InvalidPayload):
            self.cipher.decrypt(EncryptedPayload('fixture/key-alias',envelope.ciphertext),self.bound)

    def test_tamper_truncate_and_unknown_envelope_version_fail_closed(self):
        envelope=self.cipher.encrypt(self.value,self.bound)
        for position in (4,16,len(envelope.ciphertext)-1):
            changed=bytearray(envelope.ciphertext);changed[position]^=1
            with self.subTest(position=position),self.assertRaises(InvalidPayload):
                self.cipher.decrypt(EncryptedPayload(envelope.key_reference,bytes(changed)),self.bound)
        for blob in (envelope.ciphertext[:20],b'WPL2'+envelope.ciphertext[4:],b'',b'WPL1'+bytes(MAX_CIPHERTEXT_BYTES)):
            with self.assertRaises(InvalidPayload):EncryptedPayload(envelope.key_reference,blob)

    def test_rotation_resolves_recorded_key_and_missing_or_wrong_key_never_falls_back(self):
        old=self.cipher.encrypt(self.value,self.bound)
        self.keys.active='fixture/key-v2'
        self.keys.keys[self.keys.active]=AESGCM.generate_key(bit_length=256)
        new=self.cipher.encrypt(self.value,self.bound)
        self.assertEqual(self.cipher.decrypt(old,self.bound),self.value)
        self.assertEqual(self.cipher.decrypt(new,self.bound),self.value)
        self.keys.keys[old.key_reference]=AESGCM.generate_key(bit_length=256)
        with self.assertRaises(InvalidPayload):self.cipher.decrypt(old,self.bound)
        del self.keys.keys[old.key_reference]
        with self.assertRaises(PayloadKeyUnavailable):self.cipher.decrypt(old,self.bound)
        self.assertEqual(self.cipher.decrypt(new,self.bound),self.value)

    def test_size_shape_depth_cycles_and_non_json_types_are_bounded(self):
        boundary={'v':'x'*(MAX_CLEARTEXT_BYTES-len(b'{"v":""}'))}
        encrypted=self.cipher.encrypt(boundary,self.bound)
        self.assertEqual(len(encrypted.ciphertext),MAX_CIPHERTEXT_BYTES)
        self.assertEqual(self.cipher.decrypt(encrypted,self.bound),boundary)
        cycle={};cycle['cycle']=cycle
        cases=([],{'v':boundary['v']+'x'},{'v':'😀'*MAX_CLEARTEXT_BYTES},
               {1:MARKER},{'nested':{1:MARKER}},{'v':float('nan')},{'v':float('inf')},
               {'v':{MARKER}},{'v':(MARKER,)},cycle,{'v':[None]*4097})
        for value in cases:
            with self.subTest(kind=type(value).__name__),self.assertRaises(InvalidPayload) as result:
                self.cipher.encrypt(value,self.bound)
            self.assertNotIn(MARKER,str(result.exception))

    def test_invalid_scope_and_provider_configuration_has_no_defaults(self):
        for changes in ({'scope':'tenant'},{'scope_id':'caller-org'},{'actor_id':ZERO},
                        {'scope':PayloadScope.PERSONAL,'scope_id':uuid4()},
                        {'scope':PayloadScope.PLATFORM},{'purpose':'unsafe\n'+MARKER}):
            with self.assertRaises(InvalidPayload):replace(self.bound,**changes)
        for provider in (None,{},object()):
            with self.assertRaises(PayloadKeyUnavailable):PayloadCipher(provider)
        for invalid in (b'short',bytearray(32),None):
            self.keys.keys[self.keys.active]=invalid
            with self.assertRaises(PayloadKeyUnavailable):self.cipher.encrypt(self.value,self.bound)

    def test_provider_errors_are_sanitized_without_key_or_payload_values(self):
        class BrokenKeys:
            def current_reference(self):return 'fixture/key-v1'
            def resolve(self,reference):raise RuntimeError(MARKER)
        with self.assertRaises(PayloadKeyUnavailable) as result:
            PayloadCipher(BrokenKeys()).encrypt(self.value,self.bound)
        self.assertNotIn(MARKER,str(result.exception))
        self.assertTrue(result.exception.__suppress_context__)
        class BrokenReference(BrokenKeys):
            def current_reference(self):raise RuntimeError(MARKER)
        with self.assertRaises(PayloadKeyUnavailable) as result:
            PayloadCipher(BrokenReference()).encrypt(self.value,self.bound)
        self.assertNotIn(MARKER,str(result.exception))

    def test_authenticated_but_invalid_json_shape_or_duplicate_keys_is_rejected(self):
        key=self.keys.resolve(self.keys.active)
        for cleartext in (b'[]',b'{"v":1,"v":2}',b'{"v":NaN}',b'{"v":Infinity}',b'not-json',b'\xff'):
            nonce=os.urandom(12)
            blob=MAGIC+nonce+AESGCM(key).encrypt(nonce,cleartext,aad(self.bound,self.keys.active))
            with self.subTest(size=len(cleartext)),self.assertRaises(InvalidPayload):
                self.cipher.decrypt(EncryptedPayload(self.keys.active,blob),self.bound)


class PayloadStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(os.environ['WPL_MIGRATION_DATABASE_URL'])
        url=postgres_url(os.environ['WPL_APPLICATION_DATABASE_URL'],'fixture')
        if url.host!='fixture-db' or url.database!='wpl_fixture':raise RuntimeError('Refusing non-fixture crypto target.')
        cls.database=FoundationDatabase(FoundationSettings(enabled=True,application_database_url=url))

    @classmethod
    def tearDownClass(cls):cls.database.close()

    def test_ciphertext_fits_actual_schema_round_trips_and_runtime_still_cannot_read_it(self):
        keys=SyntheticKeys();cipher=PayloadCipher(keys)
        with connect() as owner:
            fixture=seed_org(owner)
            owner.execute("UPDATE wpl.organizations SET status='active' WHERE id=%s",(fixture['org'],))
            bound=PayloadBinding(PayloadScope.TENANT,fixture['org'],fixture['user'],uuid4(),uuid4(),'deliver_invitation')
            sealed=cipher.encrypt({'activation_token':MARKER},bound)
            owner.execute("""INSERT INTO wpl.secret_payloads(id,scope_kind,scope_id,org_id,key_reference,ciphertext)
                VALUES (%s,'tenant',%s,%s,%s,%s)""",(bound.payload_id,bound.scope_id,fixture['org'],sealed.key_reference,sealed.ciphertext))
        with connect() as owner:
            row=owner.execute('SELECT key_reference,ciphertext FROM wpl.secret_payloads WHERE id=%s',(bound.payload_id,)).fetchone()
            stored=EncryptedPayload(row[0],bytes(row[1]))
            self.assertNotIn(MARKER.encode(),stored.ciphertext)
            self.assertEqual(cipher.decrypt(stored,bound),{'activation_token':MARKER})
        context=RequestContext(VerifiedIdentity(fixture['user']),RequestScope.TENANT,fixture['org'])
        with self.assertRaises(DBAPIError) as result:
            with self.database.request_transaction(context) as session:
                session.execute(text('SELECT ciphertext FROM wpl.secret_payloads WHERE id=:id'),{'id':bound.payload_id})
        self.assertEqual(result.exception.orig.sqlstate,'42501')
        print('Synthetic ciphertext persisted in actual private schema; wpl_app payload read denied.',flush=True)
