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
    check_upload(file)
    file_hash, path = compute_hash_and_save(Path(settings.DATABASES_DIR), file)

    from ..services.files import detect_csv_separator
    separator = detect_csv_separator(path)
    
    # Try different encodings to read the CSV file
    headers = []
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=separator)
                headers = reader.fieldnames or []
                if headers:
                    break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if not headers:
        # Fallback: try with error replacement
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f, delimiter=separator)
                headers = reader.fieldnames or []
        except Exception:
            raise HTTPException(status_code=400, detail="Kunde inte läsa CSV-filen. Kontrollera att filen är korrekt formaterad.")
    
    if not headers:
        raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
    
    mapping = auto_map_headers(headers)

    db = DatabaseCatalog(
        name=Path(file.filename or "databas.csv").stem,
        filename=path.name,
        file_hash=file_hash,
        columns_map_json=mapping,
    )
    session.add(db)
    session.commit()
    session.refresh(db)
    log.info("Database CSV uploaded", extra={"request_id": "-", "project_id": "-", "db_id": db.id})
    return DatabaseCreateResponse(id=db.id, name=db.name, filename=db.filename, columns_map_json=mapping)


@router.get("/databases", response_model=list[DatabaseListItem])
def list_databases(session: Session = Depends(get_session)) -> list[DatabaseListItem]:
    items = session.exec(select(DatabaseCatalog).order_by(DatabaseCatalog.created_at.desc())).all()
    return [
        DatabaseListItem(
            id=i.id, name=i.name, filename=i.filename, created_at=i.created_at, updated_at=i.updated_at
        )
        for i in items
    ]


@router.patch("/databases/{database_id}")
def update_database(database_id: int, payload: dict, session: Session = Depends(get_session)) -> dict[str, str]:
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
