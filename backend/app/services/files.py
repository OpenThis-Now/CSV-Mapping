from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from ..config import settings


def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", " ")).strip().replace(" ", "_")


def check_upload(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files are allowed.")
    if hasattr(file, "size") and file.size:
        size_mb = file.size / (1024 * 1024)
        if settings.MAX_UPLOAD_MB and size_mb and size_mb > settings.MAX_UPLOAD_MB:
            raise HTTPException(status_code=413, detail=f"File too large (> {settings.MAX_UPLOAD_MB} MB).")


def compute_hash_and_save(dst_dir: Path, file: UploadFile) -> Tuple[str, Path]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(file.filename or "uploaded.csv")
    outpath = dst_dir / filename

    sha = hashlib.sha256()
    total = 0
    with outpath.open("wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            total += len(chunk)
            if settings.MAX_UPLOAD_MB and (total / (1024 * 1024)) > settings.MAX_UPLOAD_MB:
                outpath.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File too large (> {settings.MAX_UPLOAD_MB} MB)." )
            f.write(chunk)
    return sha.hexdigest(), outpath


def open_text_stream(path: Path):
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return open(path, "r", encoding=enc, newline="")
        except (UnicodeDecodeError, UnicodeError):
            continue
    return open(path, "r", encoding="utf-8", errors="replace", newline="")


def detect_csv_separator(path: Path) -> str:
    """Detect CSV separator by reading first line."""
    # Try different encodings to read the first line
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                first_line = f.readline().strip()
                if ';' in first_line and ',' not in first_line:
                    return ';'
                elif '\t' in first_line and ',' not in first_line and ';' not in first_line:
                    return '\t'
                else:
                    return ','
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # Fallback: try with error replacement
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            first_line = f.readline().strip()
            if ';' in first_line and ',' not in first_line:
                return ';'
            elif '\t' in first_line and ',' not in first_line and ';' not in first_line:
                return '\t'
            else:
                return ','
    except Exception:
        pass
    
    # Final fallback: assume comma separator
    return ','
