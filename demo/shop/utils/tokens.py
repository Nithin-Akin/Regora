import os
import jwt

def create_token(user_id: int) -> str:
    """Issue a signed JSON Web Token for a customer session."""
    return jwt.encode({"sub": str(user_id)}, os.environ["JWT_SECRET"], algorithm="HS256")

def verify_token(token: str) -> dict:
    """Validate the JWT signature and return authenticated claims."""
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
