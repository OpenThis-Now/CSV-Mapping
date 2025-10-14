from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Storage folders
    STORAGE_ROOT: Path = Field(default=Path("storage"))
    DATABASES_DIR: Path = Field(default=Path("storage/databases"))
    IMPORTS_DIR: Path = Field(default=Path("storage/imports"))
    EXPORTS_DIR: Path = Field(default=Path("storage/exports"))
    TMP_DIR: Path = Field(default=Path("storage/tmp"))
    PDFS_DIR: Path = Field(default=Path("storage/pdfs"))

    # Server / DB
    DATABASE_URL: str = Field(default="sqlite:///storage/app.db")
    POSTGRES_URL: str | None = Field(default=None)
    
    # Environment detection
    ENVIRONMENT: str = Field(default="development")
    ECHO_SQL: bool = Field(default=False)

    # Uploads & security
    MAX_UPLOAD_MB: int = Field(default=200)
    ALLOWED_EXTENSIONS: set[str] = Field(default_factory=lambda: {".csv", ".pdf"})
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", 
        "http://127.0.0.1:5173", 
        "http://localhost:5174", 
        "http://127.0.0.1:5174",
        "https://csv-mapping-frontend-production.up.railway.app",
        "https://csv-mapping-frontend-staging-experimental.up.railway.app",
        "https://csv-mapping-frontend-stagning-experimental.up.railway.app"
    ])

    # AI
    OPENAI_API_KEY: str | None = Field(default=None)
    OPENAI_API_KEY2: str | None = Field(default=None)
    OPENAI_API_KEY3: str | None = Field(default=None)
    OPENAI_API_KEY4: str | None = Field(default=None)
    OPENAI_API_KEY5: str | None = Field(default=None)
    OPENAI_API_KEY6: str | None = Field(default=None)
    OPENAI_API_KEY7: str | None = Field(default=None)
    OPENAI_API_KEY8: str | None = Field(default=None)
    OPENAI_API_KEY9: str | None = Field(default=None)
    OPENAI_API_KEY10: str | None = Field(default=None)
    AI_MODEL: str = Field(default="gpt-4o-mini")

    # Matching thresholds (defaults; can be overridden per run)
    DEFAULT_THRESHOLDS: dict[str, Any] = Field(
        default_factory=lambda: {
            "vendor_min": 80,
            "product_min": 75,
            "overall_accept": 85,
            "weights": {"vendor": 0.6, "product": 0.4},
            "sku_exact_boost": 10,
            "numeric_mismatch_penalty": 8,
        }
    )

    # Batching / performance
    MAX_ROWS_PER_BATCH: int = Field(default=20000)

    @field_validator("DEFAULT_THRESHOLDS", mode="before")
    @classmethod
    def parse_thresholds(cls, v: Any) -> dict[str, Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


def ensure_storage_dirs() -> None:
    """Create storage directories if missing."""
    for d in (settings.STORAGE_ROOT, settings.DATABASES_DIR, settings.IMPORTS_DIR, settings.EXPORTS_DIR, settings.TMP_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)


def get_environment_db_path() -> str:
    """Get environment-specific database path."""
    # Use PostgreSQL if available (Railway add-on)
    if settings.POSTGRES_URL:
        return settings.POSTGRES_URL
    
    # Use the DATABASE_URL from environment if set, otherwise use defaults
    if settings.DATABASE_URL != "sqlite:///storage/app.db":
        return settings.DATABASE_URL
    
    # Fallback to environment-specific paths
    if settings.ENVIRONMENT == "production":
        return "sqlite:///storage/production.db"
    elif settings.ENVIRONMENT == "staging":
        return "sqlite:///storage/experimental.db"
    else:
        return settings.DATABASE_URL
