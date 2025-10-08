from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import Project, DatabaseCatalog, ProjectLog, ProjectDatabase, ImportFile, MatchRun, MatchResult, AiSuggestion
from ..schemas import ProjectCreateRequest, ProjectPatchRequest, ProjectResponse

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreateRequest, session: Session = Depends(get_session)) -> ProjectResponse:
    if session.exec(select(Project).where(Project.name == payload.name)).first():
        raise HTTPException(status_code=409, detail="Projekt med detta namn finns redan.")
    p = Project(name=payload.name)
    session.add(p)
    session.commit()
    session.refresh(p)
    return ProjectResponse(id=p.id, name=p.name, status=p.status, active_database_id=p.active_database_id, active_import_id=p.active_import_id)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def patch_project(project_id: int, payload: dict, session: Session = Depends(get_session)) -> ProjectResponse:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Only update fields that are explicitly provided in the payload
    if 'name' in payload and payload['name'] is not None:
        p.name = payload['name']
    
    if 'active_database_id' in payload:
        if payload['active_database_id'] is not None:
            db = session.get(DatabaseCatalog, payload['active_database_id'])
            if not db:
                raise HTTPException(status_code=404, detail="Databas saknas.")
            old = p.active_database_id
            p.active_database_id = db.id
            session.add(ProjectLog(project_id=p.id, message=f"Bytte aktiv databas: {old} -> {db.id}"))
        else:
            old = p.active_database_id
            p.active_database_id = None
            session.add(ProjectLog(project_id=p.id, message=f"Avbockade aktiv databas: {old} -> None"))
    
    if 'active_import_id' in payload:
        if payload['active_import_id'] is not None:
            from ..models import ImportFile
            imp = session.get(ImportFile, payload['active_import_id'])
            if not imp:
                raise HTTPException(status_code=404, detail="Importfil saknas.")
            old = p.active_import_id
            p.active_import_id = imp.id
            session.add(ProjectLog(project_id=p.id, message=f"Bytte aktiv import: {old} -> {imp.id}"))
        else:
            old = p.active_import_id
            p.active_import_id = None
            session.add(ProjectLog(project_id=p.id, message=f"Avbockade aktiv import: {old} -> None"))
    
    if 'status' in payload and payload['status'] is not None:
        p.status = payload['status']
    
    session.add(p)
    session.commit()
    session.refresh(p)
    
    # print(f"DEBUG: After commit - active_database_id: {p.active_database_id}, active_import_id: {p.active_import_id}")
    
    # Let's also check what's in the database directly
    from sqlmodel import select
    db_project = session.exec(select(Project).where(Project.id == p.id)).first()
    # print(f"DEBUG: Direct DB query - active_database_id: {db_project.active_database_id}, active_import_id: {db_project.active_import_id}")
    
    return ProjectResponse(id=p.id, name=p.name, status=p.status, active_database_id=p.active_database_id, active_import_id=p.active_import_id)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    """Delete a project and all its related data"""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get all import files for this project to delete their physical files
    import_files = session.exec(
        select(ImportFile).where(ImportFile.project_id == project_id)
    ).all()
    
    # Delete physical import files from disk
    for import_file in import_files:
        file_path = Path(settings.IMPORTS_DIR) / import_file.filename
        if file_path.exists():
            file_path.unlink()
    
    # Get all match runs for this project to delete match results
    match_runs = session.exec(
        select(MatchRun).where(MatchRun.project_id == project_id)
    ).all()
    
    # Delete all match results for these match runs
    for match_run in match_runs:
        match_results = session.exec(
            select(MatchResult).where(MatchResult.match_run_id == match_run.id)
        ).all()
        for result in match_results:
            session.delete(result)
    
    # Delete all related data in correct order (respecting foreign key constraints)
    # 1. Delete AI suggestions
    ai_suggestions = session.exec(
        select(AiSuggestion).where(AiSuggestion.project_id == project_id)
    ).all()
    for suggestion in ai_suggestions:
        session.delete(suggestion)
    
    # 2. Delete match runs
    for match_run in match_runs:
        session.delete(match_run)
    
    # 3. Delete import files
    for import_file in import_files:
        session.delete(import_file)
    
    # 4. Delete project logs
    project_logs = session.exec(
        select(ProjectLog).where(ProjectLog.project_id == project_id)
    ).all()
    for log in project_logs:
        session.delete(log)
    
    # 5. Delete project-database relations
    project_databases = session.exec(
        select(ProjectDatabase).where(ProjectDatabase.project_id == project_id)
    ).all()
    for project_db in project_databases:
        session.delete(project_db)
    
    # 6. Finally, delete the project itself
    session.delete(project)
    session.commit()
    
    return {"message": "Projekt raderat."}
