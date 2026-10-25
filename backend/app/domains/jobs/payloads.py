"""Versioned encrypted job payloads with explicit key resolution and scoped AAD.

This module grants no access: enqueue/worker callers must separately validate
current actor/scope permission. No environment, file, signing-key or provider
fallback exists. Concrete key providers are injected at the trusted composition
boundary; fixture providers live only in tests.
"""
from dataclasses import dataclass,field
from enum import Enum
import json
import math
import re
import secrets
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_CLEARTEXT_BYTES=32768
MAX_CIPHERTEXT_BYTES=MAX_CLEARTEXT_BYTES+32
MAGIC=b'WPL1'
ZERO=UUID(int=0)
REFERENCE=re.compile(r'[A-Za-z0-9_.:/-]{1,128}')
PURPOSE=re.compile(r'[a-z][a-z0-9_]{0,47}')


class InvalidPayload(ValueError):
    code='invalid_secret_payload'
    def __init__(self):super().__init__('Secret payload is invalid or cannot be authenticated.')


class PayloadKeyUnavailable(RuntimeError):
    code='payload_key_unavailable'
    def __init__(self):super().__init__('Secret payload key is unavailable.')


class PayloadScope(Enum):
    TENANT='tenant'
    PERSONAL='personal'
    PLATFORM='platform'


@dataclass(frozen=True)
class PayloadBinding:
    scope: PayloadScope
    scope_id: UUID
    actor_id: UUID
    operation_id: UUID
    payload_id: UUID
    purpose: str

    def __post_init__(self):
        if (not isinstance(self.scope,PayloadScope)
                or any(not isinstance(value,UUID) for value in (self.scope_id,self.actor_id,self.operation_id,self.payload_id))
                or any(value==ZERO for value in (self.actor_id,self.operation_id,self.payload_id))
                or not isinstance(self.purpose,str) or PURPOSE.fullmatch(self.purpose) is None):
            raise InvalidPayload()
        if ((self.scope is PayloadScope.TENANT and self.scope_id==ZERO)
                or (self.scope is PayloadScope.PERSONAL and self.scope_id!=self.actor_id)
                or (self.scope is PayloadScope.PLATFORM and self.scope_id!=ZERO)):
            raise InvalidPayload()


@dataclass(frozen=True)
class EncryptedPayload:
    key_reference: str
    ciphertext: bytes=field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.key_reference,str) or REFERENCE.fullmatch(self.key_reference) is None
                or not isinstance(self.ciphertext,bytes) or not 34<=len(self.ciphertext)<=MAX_CIPHERTEXT_BYTES
                or not self.ciphertext.startswith(MAGIC)):
            raise InvalidPayload()


class KeyProvider(Protocol):
    def current_reference(self) -> str: ...
    def resolve(self,reference: str) -> bytes: ...


def validate_object(value):
    if not isinstance(value,dict):raise InvalidPayload()
    stack=[(value,0)];nodes=0
    while stack:
        item,depth=stack.pop();nodes+=1
        if nodes>4096 or depth>32:raise InvalidPayload()
        if isinstance(item,dict):
            if len(item)>4096 or any(not isinstance(key,str) or len(key)>MAX_CLEARTEXT_BYTES for key in item):
                raise InvalidPayload()
            stack.extend((entry,depth+1) for entry in item.values())
        elif isinstance(item,list):
            if len(item)>4096:raise InvalidPayload()
            stack.extend((entry,depth+1) for entry in item)
        elif isinstance(item,str):
            if len(item)>MAX_CLEARTEXT_BYTES:raise InvalidPayload()
        elif type(item) is float:
            if not math.isfinite(item):raise InvalidPayload()
        elif item is not None and type(item) not in (bool,int):
            raise InvalidPayload()


def encode_object(value):
    validate_object(value)
    try:
        result=bytearray()
        encoder=json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        for chunk in encoder.iterencode(value):
            encoded=chunk.encode('utf-8')
            if len(result)+len(encoded)>MAX_CLEARTEXT_BYTES:raise InvalidPayload()
            result.extend(encoded)
        return bytes(result)
    except (ValueError,TypeError,UnicodeError,RecursionError):
        raise InvalidPayload() from None


def aad(binding,reference):
    if not isinstance(binding,PayloadBinding):raise InvalidPayload()
    return json.dumps(['wpl.job.payload',1,reference,binding.scope.value,str(binding.scope_id),
        str(binding.actor_id),str(binding.operation_id),str(binding.payload_id),binding.purpose],
        separators=(',',':')).encode('ascii')


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise InvalidPayload()
        result[key]=value
    return result


def invalid_constant(value):
    raise InvalidPayload()


class PayloadCipher:
    def __init__(self,provider: KeyProvider):
        try:
            if not callable(getattr(provider,'current_reference',None)) or not callable(getattr(provider,'resolve',None)):
                raise ValueError
        except Exception:
            raise PayloadKeyUnavailable() from None
        self._provider=provider

    def _key(self,reference):
        try:
            value=self._provider.resolve(reference)
            if not isinstance(value,bytes) or len(value)!=32:raise ValueError
            return value
        except Exception:
            raise PayloadKeyUnavailable() from None

    def encrypt(self,value,binding: PayloadBinding) -> EncryptedPayload:
        cleartext=encode_object(value)
        if not isinstance(binding,PayloadBinding):raise InvalidPayload()
        try:
            reference=self._provider.current_reference()
            if not isinstance(reference,str) or REFERENCE.fullmatch(reference) is None:raise ValueError
        except Exception:
            raise PayloadKeyUnavailable() from None
        key=self._key(reference)
        nonce=secrets.token_bytes(12)
        ciphertext=MAGIC+nonce+AESGCM(key).encrypt(nonce,cleartext,aad(binding,reference))
        return EncryptedPayload(reference,ciphertext)

    def decrypt(self,envelope: EncryptedPayload,binding: PayloadBinding) -> dict:
        if not isinstance(envelope,EncryptedPayload):raise InvalidPayload()
        associated=aad(binding,envelope.key_reference)
        key=self._key(envelope.key_reference)
        try:
            cleartext=AESGCM(key).decrypt(envelope.ciphertext[4:16],envelope.ciphertext[16:],associated)
            if len(cleartext)>MAX_CLEARTEXT_BYTES:raise InvalidPayload()
            value=json.loads(cleartext.decode('utf-8'),object_pairs_hook=unique_object,parse_constant=invalid_constant)
            validate_object(value)
            return value
        except (InvalidTag,ValueError,TypeError,UnicodeError,RecursionError):
            raise InvalidPayload() from None
