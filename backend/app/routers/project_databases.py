from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..db import get_session
from ..models import Project, DatabaseCatalog, ProjectDatabase

router = APIRouter()


@router.post("/projects/{project_id}/databases/{database_id}")
def add_database_to_project(project_id: int, database_id: int, session: Session = Depends(get_session)):
    """Add a database to a project"""
    # Check if project exists
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Check if database exists
    database = session.get(DatabaseCatalog, database_id)
    if not database:
        raise HTTPException(status_code=404, detail="Databas saknas.")
    
    # Check if relation already exists
    existing = session.exec(
        select(ProjectDatabase).where(
            ProjectDatabase.project_id == project_id,
            ProjectDatabase.database_id == database_id
        )
    ).first()
    
    if existing:
        return {"message": "Databasen är redan kopplad till projektet."}
    
    # Create new relation
    project_db = ProjectDatabase(project_id=project_id, database_id=database_id)
    session.add(project_db)
    session.commit()
    
    return {"message": "Databas tillagd till projekt."}


@router.delete("/projects/{project_id}/databases/{database_id}")
def remove_database_from_project(project_id: int, database_id: int, session: Session = Depends(get_session)):
    """Remove a database from a project"""
    # Find the relation
    project_db = session.exec(
        select(ProjectDatabase).where(
            ProjectDatabase.project_id == project_id,
            ProjectDatabase.database_id == database_id
        )
    ).first()
    
    if not project_db:
        raise HTTPException(status_code=404, detail="Relation saknas.")
    
    session.delete(project_db)
    session.commit()
    
    return {"message": "Databas borttagen från projekt."}


@router.get("/projects/{project_id}/databases")
def get_project_databases(project_id: int, session: Session = Depends(get_session)):
    """Get all databases for a project"""
    # Check if project exists
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    # Get all databases for this project
    project_dbs = session.exec(
        select(ProjectDatabase).where(ProjectDatabase.project_id == project_id)
    ).all()
    
    database_ids = [pd.database_id for pd in project_dbs]
    
    if not database_ids:
        return []
    
    databases = session.exec(
        select(DatabaseCatalog).where(DatabaseCatalog.id.in_(database_ids))
    ).all()
    
    return databases

