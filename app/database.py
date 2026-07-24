import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cartera.db")

# Railway usa postgres:// (legacy), SQLAlchemy requiere postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite necesita check_same_thread=False para funcionar con FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency de FastAPI: provee una sesión y la cierra al terminar."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crea todas las tablas si no existen. Solo para SQLite local — en
    Postgres el esquema lo gestiona Alembic (`alembic upgrade head`)."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    from app.models import Base  # import local para evitar circular

    Base.metadata.create_all(bind=engine)
