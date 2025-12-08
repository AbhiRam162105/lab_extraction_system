from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.pool import QueuePool
from backend.core.config import get_settings

settings = get_settings()


def get_engine():
    """Create database engine with appropriate settings for SQLite or PostgreSQL."""
    db_url = settings.database.url
    
    if "sqlite" in db_url:
        # SQLite: use check_same_thread=False for multi-threading
        return create_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False}
        )
    else:
        # PostgreSQL: use connection pooling for concurrent access
        # Optimized for 32 workers with larger pool
        return create_engine(
            db_url,
            echo=False,
            poolclass=QueuePool,
            pool_size=16,          # Increased from 5 for 32 workers
            max_overflow=16,       # Extra connections when pool exhausted
            pool_timeout=10,       # Reduced from 30s for faster failure
            pool_recycle=1800,     # Recycle connections after 30 min
            pool_pre_ping=True     # Verify connection before use
        )


engine = get_engine()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

