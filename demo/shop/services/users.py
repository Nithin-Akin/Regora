from models.database import get_session
from models.entities import User
from werkzeug.security import check_password_hash, generate_password_hash

class UserService:
    """Customer lookup, account creation, and password checks."""
    @staticmethod
    def get_user(user_id: int):
        session = get_session()
        return session.get(User, user_id)

    @staticmethod
    def register(email: str, password: str):
        session = get_session()
        user = User(email=email, password_hash=generate_password_hash(password))
        session.add(User(email=email, password_hash=user.password_hash))
        session.commit()
        return user

    @staticmethod
    def check_password(email: str, password: str):
        session = get_session()
        user = session.query(User).filter_by(email=email).one()
        if not check_password_hash(user.password_hash, password):
            raise ValueError("Invalid credentials")
        return user
