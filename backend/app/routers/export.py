from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import MatchResult, MatchRun, Project

router = APIRouter()


def sanitize_header(h: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-", " ") else "_" for c in h)


def merge_rows(customer: dict[str, Any], db: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in customer.items():
        out[f"customer__{sanitize_header(k)}"] = v
    for k, v in (db or {}).items():
        out[f"database__{sanitize_header(k)}"] = v
    return out


@router.get("/projects/{project_id}/export.csv")
def export_csv(project_id: int, type: str = "approved", session: Session = Depends(get_session)) -> StreamingResponse:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    run = session.exec(select(MatchRun).where(MatchRun.project_id == project_id).order_by(MatchRun.started_at.desc())).first()
    if not run:
        raise HTTPException(status_code=400, detail="Ingen matchning att exportera.")
    
    # Filter results based on export type
    if type == "approved":
        results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id, MatchResult.decision.in_(["approved", "auto_approved", "ai_auto_approved"]))).all()
        if not results:
            raise HTTPException(status_code=400, detail="Inga godkända rader.")
    elif type == "all":
        results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id)).all()
        if not results:
            raise HTTPException(status_code=400, detail="Inga matchningar att exportera.")
    elif type == "rejected":
        results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id, MatchResult.decision.in_(["not_approved", "auto_not_approved"]))).all()
        if not results:
            raise HTTPException(status_code=400, detail="Inga avvisade rader.")
    elif type == "ai_pending":
        results = session.exec(select(MatchResult).where(MatchResult.match_run_id == run.id, MatchResult.decision == "sent_to_ai")).all()
        if not results:
            raise HTTPException(status_code=400, detail="Inga AI-väntande rader.")
    else:
        raise HTTPException(status_code=400, detail="Ogiltig exporttyp.")

    delimiter = ";"

    def row_iter() -> Iterable[bytes]:
        yield "\ufeff".encode("utf-8")
        rows = [merge_rows(r.customer_fields_json, r.db_fields_json or {}) for r in results]
        headers = sorted({k for row in rows for k in row.keys()})
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        yield buf.getvalue().encode("utf-8")

    filename = f"project_{project_id}_{type}_export.csv"
    return StreamingResponse(row_iter(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
