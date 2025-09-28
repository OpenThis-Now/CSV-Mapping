from __future__ import annotations

from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine
from .config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.ECHO_SQL)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
