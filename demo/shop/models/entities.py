from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy import Integer, String, Float

class Base(DeclarativeBase):
    pass

class User(Base):
    """A registered customer; email is unique."""
    __tablename__ = "users"
    id = mapped_column(Integer, primary_key=True)
    email = mapped_column(String, unique=True)
    password_hash = mapped_column(String)

class Order(Base):
    """Persisted checkout record and payment status."""
    __tablename__ = "orders"
    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(Integer)
    total = mapped_column(Float)
    status = mapped_column(String)
