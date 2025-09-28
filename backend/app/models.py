from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import SQLModel, Field, Relationship


class DatabaseCatalog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    filename: str
    file_hash: str = Field(index=True)
    columns_map_json: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    active_database_id: Optional[int] = Field(default=None, foreign_key="databasecatalog.id")
    active_import_id: Optional[int] = Field(default=None, foreign_key="importfile.id")
    status: str = Field(default="open", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # active_database: Optional["DatabaseCatalog"] = Relationship(back_populates=None, sa_relationship_kwargs={"lazy": "joined"})


class ProjectDatabase(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    database_id: int = Field(foreign_key="databasecatalog.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProjectLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    message: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ImportFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    original_name: str
    columns_map_json: dict[str, Any] = Field(sa_column=Column(JSON))
    row_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    thresholds_json: dict[str, Any] = Field(sa_column=Column(JSON))
    status: str = Field(default="running", index=True)


class MatchResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    match_run_id: int = Field(foreign_key="matchrun.id", index=True)
    customer_row_index: int = Field(index=True)
    decision: str = Field(default="pending", index=True)
    overall_score: float = 0.0
    reason: str = Field(default="")
    exact_match: bool = False
    customer_fields_json: dict[str, Any] = Field(sa_column=Column(JSON))
    db_fields_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    ai_status: Optional[str] = Field(default=None)
    ai_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    approved_ai_suggestion_id: Optional[int] = Field(default=None, foreign_key="aisuggestion.id")


class AiSuggestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    customer_row_index: int = Field(index=True)
    rank: int = Field(index=True)
    database_fields_json: dict[str, Any] = Field(sa_column=Column(JSON))
    confidence: float
    rationale: str = Field(sa_column=Column(Text))
    source: str = Field(default="ai")
    created_at: datetime = Field(default_factory=datetime.utcnow)
