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
        log.info(f"Starting database upload for file: {file.filename}")
        check_upload(file)
        file_hash, path = compute_hash_and_save(Path(settings.DATABASES_DIR), file)
        log.info(f"File saved to: {path}")

        from ..services.files import detect_csv_separator
        separator = detect_csv_separator(path)
        log.info(f"Detected separator: '{separator}'")
        
        # Read CSV file using the same approach as imports
        with open_text_stream(path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            headers = reader.fieldnames or []
            if not headers:
                raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
            mapping = auto_map_headers(headers)
            row_count = sum(1 for _ in reader)
        
        # Log the row count for debugging
        log.info(f"Database upload: {row_count} rows counted for {path.name}")

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
        log.info("Database CSV uploaded", extra={"request_id": "-", "project_id": "-", "db_id": db.id})
        return DatabaseCreateResponse(id=db.id, name=db.name, filename=db.filename, row_count=db.row_count, columns_map_json=mapping)
    except Exception as e:
        log.error(f"Database upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload misslyckades: {str(e)}")


@router.get("/databases", response_model=list[DatabaseListItem])
def list_databases(session: Session = Depends(get_session)) -> list[DatabaseListItem]:
    items = session.exec(select(DatabaseCatalog).order_by(DatabaseCatalog.created_at.desc())).all()
    result = [
        DatabaseListItem(
            id=i.id, name=i.name, filename=i.filename, row_count=i.row_count, created_at=i.created_at, updated_at=i.updated_at
        )
        for i in items
    ]
    log.info(f"List databases: {len(result)} databases, row_counts: {[r.row_count for r in result]}")
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
    
    log.info(f"Recounting rows for {file_path.name}, separator: '{separator}'")
    
    try:
        with open_text_stream(file_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            if not reader.fieldnames:
                raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
            row_count = sum(1 for _ in reader)
            log.info(f"Recount successful: {row_count} rows")
    except Exception as e:
        log.error(f"Recount failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Kunde inte läsa CSV-filen.")
    
    # Update the database record
    db.row_count = row_count
    session.add(db)
    session.commit()
    session.refresh(db)
    
    log.info("Database rows recounted", extra={"request_id": "-", "project_id": "-", "db_id": database_id, "row_count": row_count, "updated_row_count": db.row_count})
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
