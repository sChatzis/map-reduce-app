from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Create the SQLAlchemy Engine
# The 'pool_pre_ping=True' ensures connections are valid before use.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    # echo=True
)

# Configure the SessionLocal class
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    """Dependency to get a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        # Ensure the session is closed after the request is finished
        db.close()