"""Versioned executive changes with caller-owned commit and fixed DB operation."""
from sqlalchemy import text
from backend.app.domains.organizations.directory import require_organization_directory
from backend.app.domains.errors import AuthorizationDenied,TenantConflict

ERRORS={
    'version_conflict':'The record changed; reload before retrying.',
    'recovery_required':'Use the explicit primary recovery workflow for this organization.',
    'primary_not_active':'A verified active designated administrator is required.',
    'invalid_change':'Organization change input is invalid.',
}


def change_organization(session,identity,org_id,*,version,reason,operation,name=None,contact_email=None,home_region=None,status=None):
    require_organization_directory(session,identity,org_id)
    if type(version) is not int or version<1:
        raise TenantConflict('version_conflict',ERRORS['version_conflict'])
    # Narrow SQL function independently validates both raw input and actual context.
    with session.begin_nested():
        result=session.execute(text('SELECT wpl.change_organization(:org,:version,:operation,:name,:email,:region,:status,:reason)'),
            {'org':org_id,'version':version,'operation':operation,'name':name,'email':contact_email,
             'region':home_region,'status':status,'reason':reason}).scalar_one()
        if result is not None and 'error' in result:
            if result['error']=='forbidden':raise AuthorizationDenied()
            code=result['error'] if result['error'] in ERRORS else 'invalid_change'
            raise TenantConflict(code,ERRORS[code])
    return result
