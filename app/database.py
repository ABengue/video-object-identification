from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# Create the SQLAlchemy engine. 
# connect_args={"check_same_thread": False} is required for SQLite in multithreaded FastAPI tasks.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency injector yielding a database session context."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
