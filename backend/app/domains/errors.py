"""Stable public domain errors; never embed SQL, DSNs or secret payloads."""
class AuthorizationDenied(PermissionError):
    code = 'forbidden'
    def __init__(self):
        super().__init__('Current identity lacks permission for this operation.')

class TenantConflict(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
