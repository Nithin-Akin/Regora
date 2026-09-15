from fastapi import Header
from services.auth import AuthService

def require_user(authorization: str = Header()):
    """Authenticate an HTTP bearer token before entering protected handlers."""
    token = authorization.removeprefix("Bearer ")
    return AuthService.authenticate(token)
