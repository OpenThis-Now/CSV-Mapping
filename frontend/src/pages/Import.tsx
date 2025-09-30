import UploadArea from "@/components/UploadArea";
import api from "@/lib/api";
import { useEffect, useState } from "react";

type ImportFile = {
  id: number;
  filename: string;
  original_name: string;
  row_count: number;
  created_at: string;
  columns_map_json: Record<string, string>;
};

type Project = {
  id: number;
  name: string;
  status: string;
  active_database_id?: number | null;
  active_import_id?: number | null;
};

export default function ImportPage({ projectId }: { projectId: number }) {
  const [status, setStatus] = useState<string | null>(null);
  const [last, setLast] = useState<any | null>(null);
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [uploading, setUploading] = useState(false);

  const refreshImports = async () => {
    try {
      const res = await api.get<ImportFile[]>(`/projects/${projectId}/import`);
      setImports(res.data);
    } catch (error) {
      console.error("Failed to load imports:", error);
    }
  };

  const refreshProject = async () => {
    try {
      const res = await api.get<Project[]>(`/projects/list`);
      const currentProject = res.data.find(p => p.id === projectId);
      setProject(currentProject || null);
    } catch (error) {
      console.error("Failed to load project:", error);
    }
  };

  useEffect(() => {
    refreshImports();
    refreshProject();
  }, [projectId]);

  const onFile = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      const res = await api.post(`/projects/${projectId}/import`, fd);
      setLast(res.data);
      setStatus(`Uploaded ${res.data.row_count} products`);
      await refreshImports();
      await refreshProject();
    } finally {
      setUploading(false);
    }
  };

  const toggleImport = async (importId: number) => {
    try {
      // Check if this import is already selected
      const isCurrentlySelected = project?.active_import_id === importId;
      
      // If already selected, deselect it (set to null), otherwise select it
      const newImportId = isCurrentlySelected ? null : importId;
      
      console.log("Import.tsx: Toggling import:", { projectId, importId, newImportId, currentProject: project });
      
      const response = await api.patch(`/projects/${projectId}`, { active_import_id: newImportId });
      console.log("Import.tsx: PATCH response:", response.data);
      
      await refreshProject();
    } catch (error) {
      console.error("Failed to toggle import:", error);
    }
  };

  const deleteImport = async (importId: number) => {
    if (!confirm("Are you sure you want to delete this import file? This cannot be undone.")) {
      return;
    }
    
    try {
      await api.delete(`/projects/${projectId}/import/${importId}`);
      await refreshImports();
      await refreshProject();
    } catch (error) {
      console.error("Failed to delete import:", error);
      alert("Could not delete import file. Please try again.");
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Import customer file</h1>
      <UploadArea onFile={onFile} />
      {uploading && <div className="text-sm opacity-70">Uploading...</div>}
      {status && <div className="chip">{status}</div>}
      {/* Auto-mapping display removed for cleaner UI */}
      
      <div className="space-y-3">
        <h2 className="text-lg font-medium">Uploaded files</h2>
        {imports.length === 0 ? (
          <div className="text-sm opacity-70">No files uploaded yet</div>
        ) : (
          <div className="grid gap-3">
            {imports.map(imp => (
              <div key={imp.id} className="card">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <div className="font-medium">{imp.original_name}</div>
                    <div className="text-xs opacity-70">
                      {imp.row_count} products
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Uploaded: <span className="font-bold">{new Date(imp.created_at).toLocaleDateString('en-US')}</span> {new Date(imp.created_at).toLocaleTimeString('en-US')}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="chip">ID {imp.id}</div>
                    {project?.active_import_id === imp.id && (
                      <div className="chip bg-green-100 text-green-800 border-green-300 font-semibold">Active ✓</div>
                    )}
                    <button
                      onClick={() => deleteImport(imp.id)}
                      className="flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 rounded border border-gray-200 hover:border-red-200 transition-colors"
                      title="Delete import file"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete
                    </button>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    className={`chip ${project?.active_import_id === imp.id ? 'bg-green-100 text-green-800 border-green-300 font-semibold' : ''}`}
                    onClick={() => toggleImport(imp.id)}
                  >
                    {project?.active_import_id === imp.id ? 'Selected ✓' : 'Select this file'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
