import { useEffect, useState } from "react";
import UploadArea from "@/components/UploadArea";
import api, { DatabaseListItem, Project } from "@/lib/api";

export default function Databases({ activeProjectId }: { activeProjectId?: number | null }) {
  const [items, setItems] = useState<DatabaseListItem[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectDatabases, setProjectDatabases] = useState<Record<number, number[]>>({});
  const [uploading, setUploading] = useState(false);
  
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
  };
  
  useEffect(() => { refresh(); }, []);

  const onFile = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      await api.post("/databases", fd);
      await refresh();
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
      } else {
        // Add the database to the project
        await api.post(`/projects/${projectId}/databases/${databaseId}`);
      }
      
      // Update local state immediately
      setProjectDatabases(prev => ({
        ...prev,
        [projectId]: isCurrentlySelected 
          ? prev[projectId]?.filter(id => id !== databaseId) || []
          : [...(prev[projectId] || []), databaseId]
      }));
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

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Databases</h1>
      <UploadArea onFile={onFile} />
      {uploading && <div className="text-sm opacity-70">Uploading...</div>}
      
      <div className="grid gap-3">
        {items.map(db => (
          <div key={db.id} className="card">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-medium">{db.name}</div>
                <div className="text-xs text-gray-500 mt-1">
                  Uploaded: <span className="font-bold">{new Date(db.created_at).toLocaleDateString('en-US')}</span> {new Date(db.created_at).toLocaleTimeString('en-US')}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="chip">ID {db.id}</div>
                <button
                  onClick={() => deleteDatabase(db.id)}
                  className="px-3 py-1 text-sm bg-red-100 text-red-700 border border-red-300 rounded hover:bg-red-200"
                >
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
