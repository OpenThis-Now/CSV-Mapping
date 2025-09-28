#!/usr/bin/env python3
"""
Backend server for CSV Match Assistant
"""
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import json
from datetime import datetime
import os
import pickle

app = FastAPI(title="CSV Match Assistant")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data persistence
DATA_FILE = "backend_data.pkl"

def load_data():
    """Load data from file"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    
    # Default data
    return {
        "projects": [
            {
                "id": 1,
                "name": "Kanada kund A",
                "status": "open",
                "active_database_id": 2,
                "active_import_id": 1
            }
        ],
        "databases": [
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
        ],
        "imports": [
            {
                "id": 1,
                "filename": "nyNYTT_Import.csv",
                "original_name": "nyNYTT Import.csv",
                "row_count": 11,
                "created_at": "2025-09-27T15:04:37.010851",
                "columns_map_json": {
                    "product": "Product_name",
                    "vendor": "Supplier_name",
                    "sku": "Article_number"
                }
            }
        ]
    }

def save_data():
    """Save data to file"""
    data = {
        "projects": projects,
        "databases": databases,
        "imports": imports
    }
    with open(DATA_FILE, 'wb') as f:
        pickle.dump(data, f)

# Load initial data
data = load_data()
projects = data["projects"]
databases = data["databases"]
imports = data["imports"]

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/projects/list")
def list_projects():
    return projects

@app.post("/api/projects")
def create_project(project: dict):
    new_id = max([p["id"] for p in projects], default=0) + 1
    new_project = {
        "id": new_id,
        "name": project.get("name", "Nytt projekt"),
        "status": "open",
        "active_database_id": None,
        "active_import_id": None
    }
    projects.append(new_project)
    save_data()
    return new_project

@app.get("/api/databases")
def list_databases():
    # Sort by created_at descending (newest first)
    sorted_dbs = sorted(databases, key=lambda x: x["created_at"], reverse=True)
    return sorted_dbs

@app.post("/api/databases")
async def upload_database(file: UploadFile = File(...)):
    try:
        # Read file content safely
        content = await file.read()
        
        # Create new database entry
        new_id = max([d["id"] for d in databases], default=0) + 1
        now = datetime.now().isoformat()
        
        new_database = {
            "id": new_id,
            "name": file.filename or "Ny databas",
            "filename": file.filename or "new_database.csv",
            "created_at": now,
            "updated_at": now
        }
        databases.append(new_database)
        save_data()
        
        return new_database
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Upload failed: {str(e)}"}
        )

@app.get("/api/projects/{project_id}/import")
def list_imports(project_id: int):
    return imports

@app.post("/api/projects/{project_id}/import")
async def upload_import(project_id: int, file: UploadFile = File(...)):
    try:
        # Read file content safely
        content = await file.read()
        
        # Create new import entry
        new_id = max([i["id"] for i in imports], default=0) + 1
        now = datetime.now().isoformat()
        
        new_import = {
            "id": new_id,
            "filename": file.filename or "new_import.csv",
            "original_name": file.filename or "new_import.csv",
            "row_count": 10,  # Mock count
            "created_at": now,
            "columns_map_json": {
                "product": "Product_name",
                "vendor": "Supplier_name",
                "sku": "Article_number"
            }
        }
        imports.append(new_import)
        save_data()
        
        return new_import
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Upload failed: {str(e)}"}
        )

@app.post("/api/projects/{project_id}/match")
def run_match_old(project_id: int, request: dict):
    return {"match_run_id": 1, "status": "finished"}

@app.post("/api/projects/{project_id}/send-to-ai")
def send_to_ai(project_id: int, request: dict):
    return {"message": "Sent to AI"}

@app.post("/api/projects/{project_id}/ai/suggest")
def ai_suggest(project_id: int, request: dict):
    return []

@app.post("/api/projects/{project_id}/approve")
def approve_results(project_id: int, request: dict):
    return {"updated": 1}

@app.post("/api/projects/{project_id}/reject")
def reject_results(project_id: int, request: dict):
    return {"updated": 1}

@app.get("/api/projects/{project_id}/databases")
def get_project_databases(project_id: int):
    """Get databases for a specific project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    # Return only the active database for this project
    if project["active_database_id"]:
        active_db = next((d for d in databases if d["id"] == project["active_database_id"]), None)
        if active_db:
            return [active_db]
    
    return []

@app.post("/api/projects/{project_id}/databases/{database_id}")
def add_project_database(project_id: int, database_id: int):
    """Add a database to a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    database = next((d for d in databases if d["id"] == database_id), None)
    if not database:
        return JSONResponse(status_code=404, content={"detail": "Database not found"})
    
    # Update project's active database
    project["active_database_id"] = database_id
    save_data()
    
    return {"message": f"Database {database_id} added to project {project_id}"}

@app.delete("/api/projects/{project_id}/databases/{database_id}")
def remove_project_database(project_id: int, database_id: int):
    """Remove a database from a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    # Remove active database if it matches
    if project["active_database_id"] == database_id:
        project["active_database_id"] = None
        save_data()
    
    return {"message": f"Database {database_id} removed from project {project_id}"}

@app.delete("/api/databases/{database_id}")
def delete_database(database_id: int):
    """Delete a database file"""
    global databases
    
    # Find the database
    database = next((d for d in databases if d["id"] == database_id), None)
    if not database:
        return JSONResponse(status_code=404, content={"detail": "Database not found"})
    
    # Remove from all projects that use this database
    for project in projects:
        if project["active_database_id"] == database_id:
            project["active_database_id"] = None
    
    # Remove from databases list
    databases = [d for d in databases if d["id"] != database_id]
    
    # Try to delete the actual file
    try:
        file_path = f"storage/databases/{database['filename']}"
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted database file: {file_path}")
    except Exception as e:
        print(f"Error deleting database file: {e}")
    
    save_data()
    return {"message": f"Database {database_id} deleted successfully"}

@app.post("/api/projects/{project_id}/import/{import_id}")
def add_project_import(project_id: int, import_id: int):
    """Add an import file to a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    import_file = next((i for i in imports if i["id"] == import_id), None)
    if not import_file:
        return JSONResponse(status_code=404, content={"detail": "Import file not found"})
    
    # Update project's active import
    project["active_import_id"] = import_id
    save_data()
    
    return {"message": f"Import {import_id} added to project {project_id}"}

@app.delete("/api/projects/{project_id}/import/{import_id}")
def remove_project_import(project_id: int, import_id: int):
    """Remove an import file from a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    # Remove active import if it matches
    if project["active_import_id"] == import_id:
        project["active_import_id"] = None
        save_data()
    
    return {"message": f"Import {import_id} removed from project {project_id}"}

@app.delete("/api/imports/{import_id}")
def delete_import(import_id: int):
    """Delete an import file"""
    global imports
    
    # Find the import
    import_file = next((i for i in imports if i["id"] == import_id), None)
    if not import_file:
        return JSONResponse(status_code=404, content={"detail": "Import not found"})
    
    # Remove from all projects that use this import
    for project in projects:
        if project["active_import_id"] == import_id:
            project["active_import_id"] = None
    
    # Remove from imports list
    imports = [i for i in imports if i["id"] != import_id]
    
    # Try to delete the actual file
    try:
        file_path = f"storage/imports/{import_file['filename']}"
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted import file: {file_path}")
    except Exception as e:
        print(f"Error deleting import file: {e}")
    
    save_data()
    return {"message": f"Import {import_id} deleted successfully"}

@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, update_data: dict):
    """Update project settings"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    # Update project fields
    if "active_import_id" in update_data:
        project["active_import_id"] = update_data["active_import_id"]
    if "active_database_id" in update_data:
        project["active_database_id"] = update_data["active_database_id"]
    if "name" in update_data:
        project["name"] = update_data["name"]
    
    save_data()
    return project

@app.post("/api/projects/{project_id}/match")
def run_match(project_id: int, request: dict):
    """Run matching for a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    if not project["active_database_id"]:
        return JSONResponse(status_code=400, content={"detail": "No database selected for this project"})
    
    if not project["active_import_id"]:
        return JSONResponse(status_code=400, content={"detail": "No import file selected for this project"})
    
    # Get the selected database and import files
    database = next((d for d in databases if d["id"] == project["active_database_id"]), None)
    import_file = next((i for i in imports if i["id"] == project["active_import_id"]), None)
    
    if not database:
        return JSONResponse(status_code=400, content={"detail": "Selected database not found"})
    
    if not import_file:
        return JSONResponse(status_code=400, content={"detail": "Selected import file not found"})
    
    try:
        # Read the actual CSV files
        import pandas as pd
        import os
        
        # Read database file - try different filename variations
        db_path = f"storage/databases/{database['filename']}"
        if not os.path.exists(db_path):
            # Try with underscore instead of space
            alt_db_path = f"storage/databases/{database['filename'].replace(' ', '_')}"
            if os.path.exists(alt_db_path):
                db_path = alt_db_path
            else:
                # List available files for debugging
                available_files = os.listdir("storage/databases/")
                return JSONResponse(status_code=400, content={"detail": f"Database file not found: {db_path}. Available files: {available_files}"})
        
        # Try different encodings for database file
        db_df = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                db_df = pd.read_csv(db_path, sep=';', encoding=encoding)
                print(f"Database file loaded: {len(db_df)} rows from {db_path} with encoding {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if db_df is None:
            return JSONResponse(status_code=400, content={"detail": f"Could not read database file with any encoding: {db_path}"})
        
        # Read import file - try different filename variations
        import_path = f"storage/imports/{import_file['filename']}"
        if not os.path.exists(import_path):
            # Try with different variations
            alt_import_path = f"storage/imports/{import_file['filename'].replace(' ', '_')}"
            if os.path.exists(alt_import_path):
                import_path = alt_import_path
            else:
                # List available files for debugging
                available_files = os.listdir("storage/imports/")
                return JSONResponse(status_code=400, content={"detail": f"Import file not found: {import_path}. Available files: {available_files}"})
        
        # Try different encodings for import file
        import_df = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                import_df = pd.read_csv(import_path, sep=';', encoding=encoding)
                print(f"Import file loaded: {len(import_df)} rows from {import_path} with encoding {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if import_df is None:
            return JSONResponse(status_code=400, content={"detail": f"Could not read import file with any encoding: {import_path}"})
        
        # Create real match results based on actual data
        match_results = []
        match_id = 1
        
        # Take first 10 rows from import for demonstration
        sample_size = min(10, len(import_df))
        
        for i in range(sample_size):
            import_row = import_df.iloc[i]
            
            # Find best match in database (simple matching for demo)
            best_match_idx = 0
            best_score = 0
            
            # Simple matching logic - in real app this would be more sophisticated
            for j in range(min(100, len(db_df))):  # Limit to first 100 DB rows for demo
                db_row = db_df.iloc[j]
                
                # Simple score calculation
                score = 0
                if 'Produkt' in import_row and 'Produkt' in db_row:
                    if str(import_row['Produkt']).lower() == str(db_row['Produkt']).lower():
                        score += 50
                    elif str(import_row['Produkt']).lower() in str(db_row['Produkt']).lower():
                        score += 30
                
                if 'Leverantör' in import_row and 'Leverantör' in db_row:
                    if str(import_row['Leverantör']).lower() == str(db_row['Leverantör']).lower():
                        score += 40
                    elif str(import_row['Leverantör']).lower() in str(db_row['Leverantör']).lower():
                        score += 20
                
                if score > best_score:
                    best_score = score
                    best_match_idx = j
            
            db_row = db_df.iloc[best_match_idx]
            
            # Determine decision based on score
            decision = "auto_approved" if best_score >= 80 else "sent_to_ai"
            
            # Create customer preview
            customer_preview = {}
            for col in import_df.columns:
                if pd.notna(import_row[col]):
                    customer_preview[col] = str(import_row[col])
            
            # Create database preview
            db_preview = {}
            for col in db_df.columns:
                if pd.notna(db_row[col]):
                    db_preview[col] = str(db_row[col])
            
            match_result = {
                "id": match_id,
                "customer_row_index": i,
                "database_row_index": best_match_idx,
                "overall_score": best_score,
                "reason": f"Matchning från rad {i+1} i {import_file['original_name']} mot rad {best_match_idx+1} i {database['name']}",
                "exact_match": best_score >= 90,
                "decision": decision,
                "customer_preview": customer_preview,
                "db_preview": db_preview
            }
            
            match_results.append(match_result)
            match_id += 1
        
        print(f"Created {len(match_results)} match results")
        return {"match_run_id": 1, "status": "finished", "results": match_results}
        
    except Exception as e:
        print(f"Error during matching: {str(e)}")
        return JSONResponse(status_code=500, content={"detail": f"Error during matching: {str(e)}"})

@app.get("/api/projects/{project_id}/results")
def get_results(project_id: int):
    """Get match results for a project"""
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project:
        return JSONResponse(status_code=404, content={"detail": "Project not found"})
    
    # Get the selected database and import files
    database = next((d for d in databases if d["id"] == project["active_database_id"]), None)
    import_file = next((i for i in imports if i["id"] == project["active_import_id"]), None)
    
    if not database or not import_file:
        return []
    
    try:
        # Read the actual CSV files
        import pandas as pd
        import os
        
        # Read database file - try different filename variations
        db_path = f"storage/databases/{database['filename']}"
        if not os.path.exists(db_path):
            # Try with underscore instead of space
            alt_db_path = f"storage/databases/{database['filename'].replace(' ', '_')}"
            if os.path.exists(alt_db_path):
                db_path = alt_db_path
            else:
                return []
        
        # Try different encodings for database file
        db_df = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                db_df = pd.read_csv(db_path, sep=';', encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if db_df is None:
            return []
        
        # Read import file - try different filename variations
        import_path = f"storage/imports/{import_file['filename']}"
        if not os.path.exists(import_path):
            # Try with different variations
            alt_import_path = f"storage/imports/{import_file['filename'].replace(' ', '_')}"
            if os.path.exists(alt_import_path):
                import_path = alt_import_path
            else:
                return []
        
        # Try different encodings for import file
        import_df = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                import_df = pd.read_csv(import_path, sep=';', encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if import_df is None:
            return []
        
        # Create real match results based on actual data
        results = []
        match_id = 1
        
        # Take first 10 rows from import for demonstration
        sample_size = min(10, len(import_df))
        
        for i in range(sample_size):
            import_row = import_df.iloc[i]
            
            # Find best match in database (simple matching for demo)
            best_match_idx = 0
            best_score = 0
            
            # Simple matching logic - in real app this would be more sophisticated
            for j in range(min(100, len(db_df))):  # Limit to first 100 DB rows for demo
                db_row = db_df.iloc[j]
                
                # Simple score calculation
                score = 0
                if 'Produkt' in import_row and 'Produkt' in db_row:
                    if str(import_row['Produkt']).lower() == str(db_row['Produkt']).lower():
                        score += 50
                    elif str(import_row['Produkt']).lower() in str(db_row['Produkt']).lower():
                        score += 30
                
                if 'Leverantör' in import_row and 'Leverantör' in db_row:
                    if str(import_row['Leverantör']).lower() == str(db_row['Leverantör']).lower():
                        score += 40
                    elif str(import_row['Leverantör']).lower() in str(db_row['Leverantör']).lower():
                        score += 20
                
                if score > best_score:
                    best_score = score
                    best_match_idx = j
            
            db_row = db_df.iloc[best_match_idx]
            
            # Determine decision based on score
            decision = "auto_approved" if best_score >= 80 else "sent_to_ai"
            
            # Create customer preview
            customer_preview = {}
            for col in import_df.columns:
                if pd.notna(import_row[col]):
                    customer_preview[col] = str(import_row[col])
            
            # Create database preview
            db_preview = {}
            for col in db_df.columns:
                if pd.notna(db_row[col]):
                    db_preview[col] = str(db_row[col])
            
            result = {
                "id": match_id,
                "customer_row_index": i,
                "database_row_index": best_match_idx,
                "overall_score": best_score,
                "reason": f"Matchning från rad {i+1} i {import_file['original_name']} mot rad {best_match_idx+1} i {database['name']}",
                "exact_match": best_score >= 90,
                "decision": decision,
                "customer_preview": customer_preview,
                "db_preview": db_preview
            }
            
            results.append(result)
            match_id += 1
        
        return results
        
    except Exception as e:
        print(f"Error getting results: {str(e)}")
        return []

@app.get("/api/projects/{project_id}/export.csv")
def export_csv(project_id: int, type: str = "approved"):
    return {"message": "Export not implemented in test server"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
