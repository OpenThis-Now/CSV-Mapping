from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DatabaseCreateResponse(BaseModel):
    id: int
    name: str
    filename: str
    row_count: int
    columns_map_json: dict[str, str | None]


class DatabaseListItem(BaseModel):
    id: int
    name: str
    filename: str
    created_at: datetime
    updated_at: datetime


class ProjectCreateRequest(BaseModel):
    name: str


class ProjectPatchRequest(BaseModel):
    active_database_id: Optional[int] = Field(default=None)
    active_import_id: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None)


class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
    active_database_id: Optional[int]
    active_import_id: Optional[int]


class ImportUploadResponse(BaseModel):
    import_file_id: int
    filename: str
    row_count: int
    columns_map_json: dict[str, str | None]


class Thresholds(BaseModel):
    vendor_min: int = 80
    product_min: int = 75
    overall_accept: int = 85
    weights: dict[str, float] = Field(default_factory=lambda: {"vendor": 0.6, "product": 0.4})
    sku_exact_boost: int = 10
    numeric_mismatch_penalty: int = 8


class MatchRequest(BaseModel):
    thresholds: Optional[Thresholds] = None
    match_new_only: Optional[bool] = False


class MatchRunResponse(BaseModel):
    match_run_id: int
    status: str


class MatchResultItem(BaseModel):
    id: int
    customer_row_index: int
    decision: str
    overall_score: float
    reason: str
    exact_match: bool
    customer_preview: dict[str, Any]
    db_preview: Optional[dict[str, Any]]
    ai_confidence: Optional[float] = None


class ApproveRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
    customer_row_indices: list[int] = Field(default_factory=list)

class ApproveAIRequest(BaseModel):
    customer_row_index: int
    ai_suggestion_id: int


class AiSuggestRequest(BaseModel):
    customer_row_indices: list[int] = Field(default_factory=list)
    max_suggestions: int = 3


class AiSuggestionItem(BaseModel):
    id: Optional[int] = None
    customer_row_index: int
    rank: int
    database_fields_json: dict[str, Any]
    confidence: float
    rationale: str
    source: str


class CombineImportsRequest(BaseModel):
    import_ids: list[int] = Field(default_factory=list)


class RejectedProductUpdateRequest(BaseModel):
    company_id: Optional[str] = None
    pdf_filename: Optional[str] = None
    pdf_source: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
