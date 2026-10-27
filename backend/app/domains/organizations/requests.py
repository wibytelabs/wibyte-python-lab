"""Fixed executive request fields; no identity, capability or designation input."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator


class ExecutiveChange(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(strict=True,ge=1)
    reason: str=Field(min_length=5,max_length=1000)

    @field_validator('reason')
    @classmethod
    def reason_required(cls,value):
        value=value.strip()
        if len(value)<5:raise ValueError('A reason is required.')
        return value


class OrganizationPatch(ExecutiveChange):
    name: str | None=Field(default=None,min_length=1,max_length=160)
    contact_email: str | None=Field(default=None,min_length=3,max_length=254)
    home_region: str | None=Field(default=None,min_length=1,max_length=64,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')

    @field_validator('name')
    @classmethod
    def name_valid(cls,value):
        if value is not None:
            value=value.strip()
            if not value or any(ord(char)<32 or ord(char)==127 for char in value):raise ValueError('Invalid organization name.')
        return value

    @field_validator('contact_email')
    @classmethod
    def email_valid(cls,value):
        if value is not None:
            value=value.strip().lower()
            if value.count('@')!=1 or '.' not in value.split('@')[1] or any(char.isspace() or ord(char)<33 for char in value):
                raise ValueError('Invalid contact email.')
        return value

    @model_validator(mode='after')
    def change_required(self):
        if all(value is None for value in (self.name,self.contact_email,self.home_region)):raise ValueError('Supply a metadata change.')
        return self


class OrganizationStatus(ExecutiveChange):
    status: Literal['active','suspended']


class OrganizationCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    name: str=Field(min_length=1,max_length=160)
    organization_type: Literal['school','university','training','other']
    contact_email: str=Field(min_length=3,max_length=254)
    primary_admin_email: str=Field(min_length=3,max_length=254)
    home_region: str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    reason: str=Field(min_length=5,max_length=1000)

    @field_validator('name')
    @classmethod
    def name_valid(cls,value):return OrganizationPatch.name_valid(value)

    @field_validator('contact_email','primary_admin_email')
    @classmethod
    def email_valid(cls,value):
        value=OrganizationPatch.email_valid(value)
        local,domain=value.split('@')
        if not local or domain.startswith('.') or domain.endswith('.'):raise ValueError('Invalid email.')
        return value

    @field_validator('reason')
    @classmethod
    def reason_required(cls,value):return ExecutiveChange.reason_required(value)
