from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import DatabaseCatalog
from ..schemas import DatabaseCreateResponse, DatabaseListItem
from ..services.files import check_upload, compute_hash_and_save, open_text_stream
from ..services.mapping import auto_map_headers

router = APIRouter()
log = logging.getLogger("app.databases")


@router.post("/databases", response_model=DatabaseCreateResponse)
def upload_database_csv(file: UploadFile = File(...), session: Session = Depends(get_session)) -> Any:
    try:
        check_upload(file)
        file_hash, path = compute_hash_and_save(Path(settings.DATABASES_DIR), file)

        from ..services.files import detect_csv_separator
        separator = detect_csv_separator(path)
        
        # Read CSV file using the same approach as imports
        with open_text_stream(path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            if not headers:
                raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
            mapping = auto_map_headers(headers)
            row_count = sum(1 for _ in reader)

        db = DatabaseCatalog(
            name=Path(file.filename or "databas.csv").stem,
            filename=path.name,
            file_hash=file_hash,
            columns_map_json=mapping,
            row_count=row_count,
        )
        session.add(db)
        session.commit()
        session.refresh(db)
        return DatabaseCreateResponse(id=db.id, name=db.name, filename=db.filename, row_count=db.row_count, columns_map_json=mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload misslyckades: {str(e)}")


@router.get("/databases", response_model=list[DatabaseListItem])
def list_databases(session: Session = Depends(get_session)) -> list[DatabaseListItem]:
    items = session.exec(select(DatabaseCatalog).order_by(DatabaseCatalog.created_at.desc())).all()
    result = []
    for i in items:
        # Debug: check if row_count exists
        row_count = getattr(i, 'row_count', None)
        result.append(DatabaseListItem(
            id=i.id, name=i.name, filename=i.filename, row_count=row_count or 0, created_at=i.created_at, updated_at=i.updated_at
        ))
    return result


@router.patch("/databases/{database_id}")
def update_database(database_id: int, payload: dict, session: Session = Depends(get_session)) -> dict[str, str]:
    """Update database name or other fields"""
    db = session.get(DatabaseCatalog, database_id)
    if not db:
        raise HTTPException(status_code=404, detail="Databas saknas.")
    
    # Only update fields that are explicitly provided in the payload
    if 'name' in payload and payload['name'] is not None:
        db.name = payload['name']
    
    session.add(db)
    session.commit()
    
    log.info("Database updated", extra={"request_id": "-", "project_id": "-", "db_id": database_id})
    return {"message": "Databas uppdaterad."}


@router.patch("/databases/{database_id}/recount")
def recount_database_rows(database_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    """Recount rows for an existing database"""
    db = session.get(DatabaseCatalog, database_id)
    if not db:
        raise HTTPException(status_code=404, detail="Databas saknas.")
    
    # Get the file path
    file_path = Path(settings.DATABASES_DIR) / db.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Databasfil saknas på disk.")
    
    # Count rows in the file using the same approach as imports
    from ..services.files import detect_csv_separator, open_text_stream
    separator = detect_csv_separator(file_path)
    
    try:
        with open_text_stream(file_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            if not reader.fieldnames:
                raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
            row_count = sum(1 for _ in reader)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Kunde inte läsa CSV-filen.")
    
    # Update the database record using raw SQL to ensure the column exists
    from sqlalchemy import text
    try:
        session.execute(text("ALTER TABLE databasecatalog ADD COLUMN IF NOT EXISTS row_count INTEGER DEFAULT 0"))
        session.commit()
    except Exception:
        pass  # Column might already exist
    
    # Update the database record
    db.row_count = row_count
    session.add(db)
    session.commit()
    session.refresh(db)
    
    return {"message": f"Databas uppdaterad med {row_count} rader."}


@router.delete("/databases/{database_id}")
def delete_database(database_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    db = session.get(DatabaseCatalog, database_id)
    if not db:
        raise HTTPException(status_code=404, detail="Databas saknas.")
    
    # Remove file from disk
    file_path = Path(settings.DATABASES_DIR) / db.filename
    if file_path.exists():
        file_path.unlink()
    
    # Remove from database
    session.delete(db)
    session.commit()
    
    log.info("Database deleted", extra={"request_id": "-", "project_id": "-", "db_id": database_id})
    return {"message": "Databas raderad."}
