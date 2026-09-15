from utils.tokens import verify_token, create_token
from services.users import UserService

class AuthService:
    """Authentication: validate bearer credentials and start customer sessions."""
    @staticmethod
    def authenticate(token: str):
        claims = verify_token(token)
        return UserService.get_user(int(claims["sub"]))

    @staticmethod
    def login(email: str, password: str):
        user = UserService.check_password(email, password)
        return create_token(user.id)
