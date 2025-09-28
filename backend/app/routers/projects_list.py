from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Project
from ..schemas import ProjectResponse

router = APIRouter()


@router.get("/projects/list", response_model=list[ProjectResponse])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectResponse]:
    ps = session.exec(select(Project).order_by(Project.created_at.desc())).all()
    return [ProjectResponse(id=p.id, name=p.name, status=p.status, active_database_id=p.active_database_id, active_import_id=p.active_import_id) for p in ps]
