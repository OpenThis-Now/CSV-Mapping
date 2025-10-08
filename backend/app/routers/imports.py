from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import ImportFile, Project
from ..schemas import ImportUploadResponse
from ..services.files import check_upload, compute_hash_and_save, open_text_stream, detect_csv_separator
from ..services.mapping import auto_map_headers

router = APIRouter()


@router.post("/projects/{project_id}/import", response_model=ImportUploadResponse)
def upload_import_csv(project_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> ImportUploadResponse:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    check_upload(file)
    _, path = compute_hash_and_save(Path(settings.IMPORTS_DIR), file)

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


@router.get("/projects/{project_id}/import/{import_id}/data")
def get_import_data(project_id: int, import_id: int, session: Session = Depends(get_session)) -> List[Dict[str, Any]]:
    """Get CSV data for editing"""
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    imp = session.get(ImportFile, import_id)
    if not imp or imp.project_id != project_id:
        raise HTTPException(status_code=404, detail="Importfil saknas.")
    
    # Read CSV file
    file_path = Path(settings.IMPORTS_DIR) / imp.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CSV-fil saknas på disk.")
    
    separator = detect_csv_separator(file_path)
    
    try:
        with open_text_stream(file_path) as f:
            reader = csv.DictReader(f, delimiter=separator)
            data = list(reader)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kunde inte läsa CSV-fil: {str(e)}")


@router.put("/projects/{project_id}/import/{import_id}/data")
def update_import_data(project_id: int, import_id: int, data: List[Dict[str, Any]], session: Session = Depends(get_session)) -> Dict[str, str]:
    """Update CSV data"""
    # print(f"DEBUG: update_import_data called with project_id={project_id}, import_id={import_id}, data_length={len(data)}")
    
    p = session.get(Project, project_id)
    if not p:
        # print(f"DEBUG: Project {project_id} not found")
        raise HTTPException(status_code=404, detail="Projekt saknas.")
    
    imp = session.get(ImportFile, import_id)
    if not imp or imp.project_id != project_id:
        # print(f"DEBUG: ImportFile {import_id} not found or wrong project")
        raise HTTPException(status_code=404, detail="Importfil saknas.")
    
    # Write updated CSV file
    file_path = Path(settings.IMPORTS_DIR) / imp.filename
    # print(f"DEBUG: File path: {file_path}")
    # print(f"DEBUG: File exists: {file_path.exists()}")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="CSV-fil saknas på disk.")
    
    try:
        separator = detect_csv_separator(file_path)
        # print(f"DEBUG: Detected separator: '{separator}'")
        
        # Get column headers from first row or existing mapping
        if data:
            headers = list(data[0].keys())
            # print(f"DEBUG: Headers from data: {headers}")
        else:
            # If no data, use headers from mapping
            headers = list(imp.columns_map_json.keys())
            # print(f"DEBUG: Headers from mapping: {headers}")
        
        # print(f"DEBUG: Writing {len(data)} rows to file")
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=separator)
            writer.writeheader()
            writer.writerows(data)
        
        # print(f"DEBUG: File written successfully")
        
        # Update row count
        imp.row_count = len(data)
        session.add(imp)
        session.commit()
        
        # print(f"DEBUG: Database updated, row_count={len(data)}")
        
        return {"message": "CSV-data uppdaterad.", "row_count": len(data)}
    except Exception as e:
        # print(f"DEBUG: Exception occurred: {str(e)}")
        # print(f"DEBUG: Exception type: {type(e)}")
        import traceback
        # print(f"DEBUG: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Kunde inte skriva CSV-fil: {str(e)}")
