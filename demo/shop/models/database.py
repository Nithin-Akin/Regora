from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine("sqlite:///shop.db")
Session = sessionmaker(bind=engine)

def get_session():
    """Create a transaction-scoped database connection."""
    return Session()
