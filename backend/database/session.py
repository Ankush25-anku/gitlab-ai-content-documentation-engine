"""Engine and session factory. SQLite locally, Postgres (Supabase) in production."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import get_settings
from backend.database.models import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool  # one shared in-memory DB for tests
            _engine = create_engine(url, **kwargs)
        else:
            _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Used by tests to switch databases."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    """Create tables when running on SQLite. On Supabase, run the SQL migrations instead."""
    engine = get_engine()
    if get_settings().is_sqlite:
        Base.metadata.create_all(engine)


def new_session() -> Session:
    get_engine()
    return _SessionLocal()


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()
