import { useEffect, useState } from "react";
import UploadArea from "@/components/UploadArea";
import api, { DatabaseListItem, Project } from "@/lib/api";

export default function Databases({ activeProjectId }: { activeProjectId?: number | null }) {
  const [items, setItems] = useState<DatabaseListItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectDatabases, setProjectDatabases] = useState<Record<number, number[]>>({});
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const [editingDatabase, setEditingDatabase] = useState<number | null>(null);
  const [editName, setEditName] = useState<string>("");
  
  const refresh = async () => {
    const [databasesRes, projectsRes] = await Promise.all([
      api.get<DatabaseListItem[]>("/databases"),
      api.get<Project[]>("/projects/list")
    ]);
    setItems(databasesRes.data);
    setProjects(projectsRes.data);
    
    // Load project-database relations
    const relations: Record<number, number[]> = {};
    for (const project of projectsRes.data) {
      try {
        const projectDbs = await api.get(`/projects/${project.id}/databases`);
        relations[project.id] = projectDbs.data.map((db: any) => db.id);
      } catch (error) {
        relations[project.id] = [];
      }
    }
    setProjectDatabases(relations);
    setLastRefresh(Date.now());
  };
  
  useEffect(() => { refresh(); }, []);
  
  // Refresh when activeProjectId changes (e.g., when a new project is created)
  useEffect(() => { 
    if (activeProjectId) {
      refresh(); 
    }
  }, [activeProjectId]);
  
  // Also refresh when component becomes visible (in case user navigated from projects page)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        refresh();
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);
  

  const onFile = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    setStatus(null); // Clear previous status
    try {
      const res = await api.post("/databases", fd);
      setStatus(`Uploaded ${res.data.row_count} products`);
      await refresh();
    } catch (error: any) {
      console.error("Upload failed:", error);
      const errorMessage = error.response?.data?.detail || error.message || "Upload failed";
      setStatus(`Error: ${errorMessage}`);
    } finally {
      setUploading(false);
    }
  };

  const toggleDatabase = async (projectId: number, databaseId: number) => {
    try {
      const isCurrentlySelected = projectDatabases[projectId]?.includes(databaseId) || false;
      
      if (isCurrentlySelected) {
        // Remove the database from the project
        await api.delete(`/projects/${projectId}/databases/${databaseId}`);
        // Also clear the active database if it was this one
        await api.patch(`/projects/${projectId}`, { active_database_id: null });
      } else {
        // Add the database to the project
        await api.post(`/projects/${projectId}/databases/${databaseId}`);
        // Also set this as the active database
        await api.patch(`/projects/${projectId}`, { active_database_id: databaseId });
      }
      
      // Refresh everything to get the latest state from backend
      await refresh();
    } catch (error) {
      console.error("Failed to toggle database:", error);
    }
  };

  const deleteDatabase = async (databaseId: number) => {
    if (!confirm("Are you sure you want to delete this database? This cannot be undone.")) {
      return;
    }
    
    try {
      await api.delete(`/databases/${databaseId}`);
      await refresh();
    } catch (error) {
      console.error("Failed to delete database:", error);
      alert("Could not delete database. Please try again.");
    }
  };

  const startEdit = (database: DatabaseListItem) => {
    setEditingDatabase(database.id);
    setEditName(database.name);
  };

  const cancelEdit = () => {
    setEditingDatabase(null);
    setEditName("");
  };

  const saveEdit = async (databaseId: number) => {
    if (!editName.trim()) {
      alert("Database name cannot be empty");
      return;
    }
    
    try {
      await api.patch(`/databases/${databaseId}`, { name: editName.trim() });
      setEditingDatabase(null);
      setEditName("");
      await refresh();
    } catch (error) {
      console.error("Failed to update database name:", error);
      alert("Could not update database name. Please try again.");
    }
  };


  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Databases</h1>
        <button 
          onClick={refresh}
          className="px-3 py-1 text-sm bg-blue-100 text-blue-700 border border-blue-300 rounded hover:bg-blue-200"
        >
          Refresh
        </button>
      </div>
      <UploadArea onFile={onFile} />
      {uploading && <div className="text-sm opacity-70">Uploading...</div>}
      {status && <div className="chip">{status}</div>}
      
      <div className="grid gap-3">
        {items.map(db => (
          <div key={db.id} className="card">
            <div className="flex items-center justify-between mb-3">
              <div>
                {editingDatabase === db.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="px-2 py-1 border border-gray-300 rounded text-sm font-medium"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveEdit(db.id);
                        if (e.key === 'Escape') cancelEdit();
                      }}
                    />
                    <button
                      onClick={() => saveEdit(db.id)}
                      className="px-2 py-1 text-xs bg-green-100 text-green-700 border border-green-300 rounded hover:bg-green-200"
                    >
                      Save
                    </button>
                    <button
                      onClick={cancelEdit}
                      className="px-2 py-1 text-xs bg-gray-100 text-gray-700 border border-gray-300 rounded hover:bg-gray-200"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="font-medium flex items-center gap-2">
                    {db.name}
                    <button
                      onClick={() => startEdit(db)}
                      className="text-gray-400 hover:text-gray-600 text-sm p-1"
                      title="Edit database name"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                      </svg>
                    </button>
                  </div>
                )}
        <div className="text-xs opacity-70">
          {!db.row_count || db.row_count === 0 ? 'products' : `${db.row_count} products`}
        </div>
                <div className="text-xs text-gray-500 mt-1">
                  Uploaded: <span className="font-bold">{new Date(db.created_at).toLocaleDateString('en-US')}</span> {new Date(db.created_at).toLocaleTimeString('en-US')}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="chip">ID {db.id}</div>
                <button
                  onClick={() => deleteDatabase(db.id)}
                  className="flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 rounded border border-gray-200 hover:border-red-200 transition-colors"
                  title="Delete database"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Delete
                </button>
              </div>
            </div>
            
            <div className="space-y-2">
              <div className="text-sm font-medium">Select for projects:</div>
              <div className="flex flex-wrap gap-2">
                {projects.map(project => {
                  const isSelected = projectDatabases[project.id]?.includes(db.id) || false;
                  const isActiveProject = activeProjectId === project.id;
                  
                  return (
                    <button
                      key={project.id}
                      className={`chip ${
                        isSelected 
                          ? (isActiveProject 
                              ? 'bg-green-100 text-green-800 border-green-300 font-semibold' 
                              : 'bg-blue-100 border-blue-500')
                          : ''
                      }`}
                      onClick={() => toggleDatabase(project.id, db.id)}
                    >
                      {project.name} {isSelected ? '✓' : ''}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
