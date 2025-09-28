#!/usr/bin/env python3
"""
Simple backend server for testing
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="CSV Match Assistant")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/projects/list")
def list_projects():
    return [
        {
            "id": 1,
            "name": "Kanada kund A",
            "status": "open",
            "active_database_id": 2,
            "active_import_id": 1
        }
    ]

@app.get("/api/databases")
def list_databases():
    return [
        {
            "id": 1,
            "name": "test_database",
            "filename": "test_database.csv",
            "created_at": "2025-09-27T09:51:24.936552",
            "updated_at": "2025-09-27T09:51:24.936560"
        },
        {
            "id": 2,
            "name": "NYTT DB",
            "filename": "NYTT_DB.csv",
            "created_at": "2025-09-27T10:54:06.617490",
            "updated_at": "2025-09-27T10:54:06.617514"
        }
    ]

@app.post("/api/projects")
def create_project(project: dict):
    return {
        "id": 2,
        "name": project.get("name", "Nytt projekt"),
        "status": "open",
        "active_database_id": None,
        "active_import_id": None
    }

@app.post("/api/databases")
def upload_database(file: dict):
    return {
        "id": 3,
        "name": "Ny databas",
        "filename": "new_database.csv",
        "created_at": "2025-09-27T20:30:00.000000",
        "updated_at": "2025-09-27T20:30:00.000000"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
