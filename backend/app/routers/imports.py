from __future__ import annotations

import csv
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project
from ..schemas import ImportUploadResponse
from ..services.files import check_upload, compute_hash_and_save, open_text_stream
from ..services.mapping import auto_map_headers

router = APIRouter()


@router.post("/projects/{project_id}/import", response_model=ImportUploadResponse)
def upload_import_csv(project_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> ImportUploadResponse:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    check_upload(file)
    _, path = compute_hash_and_save(Path(settings.IMPORTS_DIR), file)

    from ..services.files import detect_csv_separator
    separator = detect_csv_separator(path)
    
    with open_text_stream(path) as f:
        reader = csv.DictReader(f, delimiter=separator)
        headers = reader.fieldnames or []
        if not headers:
            raise HTTPException(status_code=400, detail="CSV saknar rubriker.")
        mapping = auto_map_headers(headers)
        count = sum(1 for _ in reader)

    imp = ImportFile(
        project_id=project_id,
        filename=path.name,
        original_name=file.filename or path.name,
        columns_map_json=mapping,
        row_count=count,
    )
    session.add(imp)
    session.commit()
    session.refresh(imp)
    return ImportUploadResponse(import_file_id=imp.id, filename=imp.filename, row_count=imp.row_count, columns_map_json=mapping)


@router.get("/projects/{project_id}/import")
def list_import_files(project_id: int, session: Session = Depends(get_session)):
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    imports = session.exec(select(ImportFile).where(ImportFile.project_id == project_id).order_by(ImportFile.created_at.desc())).all()
    return [
        {
            "id": imp.id,
            "filename": imp.filename,
            "original_name": imp.original_name,
            "row_count": imp.row_count,
            "created_at": imp.created_at,
            "columns_map_json": imp.columns_map_json,
            "has_sds_urls": _has_sds_url_column(imp.columns_map_json)
        }
        for imp in imports
    ]


def _has_sds_url_column(columns_map: dict[str, str]) -> bool:
    """Check if import file has SDS URL column with actual URLs"""
    url_field = columns_map.get("url")
    if not url_field:
        return False
    
    # Check if the URL field exists in the mapping
    return url_field != "URL"  # If it's mapped to something other than default "URL", it has URLs


@router.delete("/projects/{project_id}/import/{import_id}")
def delete_import_file(project_id: int, import_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    imp = session.get(ImportFile, import_id)
    if not imp or imp.project_id != project_id:
        raise HTTPException(status_code=404, detail="Importfil saknas.")
    
    # Remove file from disk
    file_path = Path(settings.IMPORTS_DIR) / imp.filename
    if file_path.exists():
        file_path.unlink()
    
    # Remove from database
    session.delete(imp)
    session.commit()
    
    return {"message": "Importfil raderad."}
