from __future__ import annotations

from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine
from .config import settings, get_environment_db_path

# Use environment-specific database path
database_url = get_environment_db_path()
engine = create_engine(database_url, echo=settings.ECHO_SQL)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
