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
    
    # Run migrations for existing tables
    _run_migrations()

def _run_migrations() -> None:
    """Run database migrations for existing tables"""
    from sqlalchemy import text
    import logging
    
    logger = logging.getLogger("app")
    
    try:
        with engine.connect() as conn:
            # Check if row_count column exists in databasecatalog
            result = conn.execute(text("PRAGMA table_info(databasecatalog)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'row_count' not in columns:
                logger.info("Adding row_count column to databasecatalog table")
                conn.execute(text('ALTER TABLE databasecatalog ADD COLUMN row_count INTEGER DEFAULT 0'))
                conn.commit()
                logger.info("Successfully added row_count column to databasecatalog")
            
            # Check if row_count column exists in importfile
            result = conn.execute(text("PRAGMA table_info(importfile)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'row_count' not in columns:
                logger.info("Adding row_count column to importfile table")
                conn.execute(text('ALTER TABLE importfile ADD COLUMN row_count INTEGER DEFAULT 0'))
                conn.commit()
                logger.info("Successfully added row_count column to importfile")
                
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        # Don't raise - let the app start even if migrations fail