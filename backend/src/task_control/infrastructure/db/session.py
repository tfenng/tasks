from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from task_control.config import get_settings
from task_control.infrastructure.db.models import Base

_settings = get_settings()
engine = create_engine(
    _settings.database_url,
    echo=_settings.database_echo,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    Base.metadata.drop_all(bind=engine)
