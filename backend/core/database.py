from sqlmodel import create_engine, SQLModel, Session
from backend.core.config import get_settings

settings = get_settings()

# For SQLite, we need connect_args to allow multithreading access if needed (though check_same_thread=False is the usual fix)
connect_args = {"check_same_thread": False} if "sqlite" in settings.database.url else {}

engine = create_engine(settings.database.url, echo=False, connect_args=connect_args)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
