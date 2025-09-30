import UploadArea from "@/components/UploadArea";
import api from "@/lib/api";
import { useEffect, useState } from "react";
import { useToast } from "@/contexts/ToastContext";

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
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pdfUploading, setPdfUploading] = useState(false);
  const { showToast } = useToast();

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

  const onPDFFiles = async (files: File[]) => {
    setSelectedFiles(files);
    setPdfUploading(true);
    
    try {
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });
      
      const res = await api.post(`/projects/${projectId}/pdf-import`, formData);
      
      setLast(res.data);
      setStatus(`Processed ${files.length} PDF files, extracted ${res.data.row_count} products`);
      showToast(`Successfully processed ${files.length} PDF files`, 'success');
      
      await refreshImports();
      await refreshProject();
    } catch (error: any) {
      console.error("PDF upload failed:", error);
      const errorMessage = error.response?.data?.detail || "PDF processing failed";
      showToast(`PDF processing failed: ${errorMessage}`, 'error');
      setStatus(`Failed to process PDF files: ${errorMessage}`);
    } finally {
      setPdfUploading(false);
      setSelectedFiles([]);
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Customer Import</h1>
        <div className="text-sm text-gray-600">
          Project: {project?.name || 'Loading...'}
        </div>
      </div>

      {/* CSV Upload Section */}
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold mb-2">Upload CSV File</h2>
          <p className="text-sm text-gray-600 mb-4">
            Upload a CSV file with customer product data for matching.
          </p>
        </div>
        
        <UploadArea onFile={onFile} accept=".csv" />
        
        {uploading && (
          <div className="flex items-center gap-2 text-blue-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
            Uploading CSV file...
          </div>
        )}
      </div>

      {/* PDF Upload Section */}
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold mb-2">Upload PDF Files</h2>
          <p className="text-sm text-gray-600 mb-4">
            Upload multiple PDF files (SDS documents) for AI-powered product information extraction.
            The system will read the first 3 pages of each PDF and extract product names, article numbers, and supplier information.
          </p>
        </div>
        
        <UploadArea 
          onFiles={onPDFFiles}
          accept=".pdf"
          multiple={true}
        />
        
        {selectedFiles.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium mb-2">Selected files:</h3>
            <ul className="text-sm text-gray-600">
              {selectedFiles.map((file, index) => (
                <li key={index}>• {file.name}</li>
              ))}
            </ul>
          </div>
        )}
        
        {pdfUploading && (
          <div className="flex items-center gap-2 text-blue-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
            Processing PDF files with AI...
          </div>
        )}
      </div>

      {status && (
        <div className={`p-3 rounded text-sm ${
          status.includes('Failed') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          {status}
        </div>
      )}
      
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
