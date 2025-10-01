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
  has_sds_urls?: boolean;
};

type Project = {
  id: number;
  name: string;
  status: string;
  active_database_id?: number | null;
  active_import_id?: number | null;
};

export default function ImportPage({ projectId, onImportChange }: { projectId: number; onImportChange?: () => void }) {
  const [status, setStatus] = useState<string | null>(null);
  const [last, setLast] = useState<any | null>(null);
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [urlEnhancing, setUrlEnhancing] = useState<number | null>(null);
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
      
      // Notify parent component about import change
      if (onImportChange) {
        onImportChange();
      }
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
      
      // Notify parent component about import change
      if (onImportChange) {
        onImportChange();
      }
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
      
      // Notify parent component about import change
      if (onImportChange) {
        onImportChange();
      }
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
      
      // Notify parent component about import change
      if (onImportChange) {
        onImportChange();
      }
    } catch (error) {
      console.error("Failed to delete import:", error);
      alert("Could not delete import file. Please try again.");
    }
  };

  const enhanceWithUrls = async (importId: number) => {
    if (!confirm("This will enhance the import file by extracting data from SDS URLs. This may take several minutes. Continue?")) {
      return;
    }
    
    setUrlEnhancing(importId);
    try {
      // First set this import as active
      await api.patch(`/projects/${projectId}`, { active_import_id: importId });
      
      // Then enhance with URLs
      const res = await api.post(`/projects/${projectId}/enhance-with-urls`);
      showToast(`Successfully enhanced import file with SDS data`, 'success');
      setStatus(`Enhanced import file created with ${res.data.row_count} rows`);
      await refreshImports();
      await refreshProject();
      
      // Notify parent component about import change
      if (onImportChange) {
        onImportChange();
      }
    } catch (error: any) {
      console.error("URL enhancement failed:", error);
      const errorMessage = error.response?.data?.detail || "URL enhancement failed";
      showToast(`URL enhancement failed: ${errorMessage}`, 'error');
      setStatus(`URL enhancement failed: ${errorMessage}`);
    } finally {
      setUrlEnhancing(null);
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

      {/* Upload Sections - Side by Side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* CSV Upload Section */}
        <div className="rounded-xl p-4 border bg-white border-slate-200">
          <div className="flex items-center gap-2 mb-3">
            <div className="rounded-lg bg-blue-600/10 p-1.5">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                className="h-5 w-5 text-blue-600"
                fill="none"
                stroke="currentColor"
              >
                <rect x="3" y="5" width="18" height="14" rx="2" ry="2" strokeWidth="1.5" />
                <path d="M3 10h18M8 5v14M16 5v14" strokeWidth="1.5" />
              </svg>
            </div>
            <h3 className="text-base font-semibold">Upload CSV</h3>
            <span className="ml-auto text-xs rounded bg-slate-100 px-2 py-0.5">.csv</span>
          </div>

          <div className="text-center p-4 border-2 border-dashed border-slate-200 rounded-lg hover:border-blue-300 transition-colors">
            <UploadArea onFile={onFile} accept=".csv" />
          </div>
          
          {uploading && (
            <div className="flex items-center justify-center gap-2 text-blue-600 mt-3">
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600"></div>
              <span className="text-sm">Uploading...</span>
            </div>
          )}
        </div>

        {/* PDF Upload Section */}
        <div className="rounded-xl p-4 border bg-white border-slate-200">
          <div className="flex items-center gap-2 mb-3">
            <div className="rounded-lg bg-rose-600/10 p-1.5">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                className="h-5 w-5 text-rose-600"
                fill="none"
                stroke="currentColor"
              >
                <path d="M8 4h5.5L20 10.5V20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" strokeWidth="1.5" />
                <path d="M13.5 4V10.5H20" strokeWidth="1.5" />
              </svg>
            </div>
            <h3 className="text-base font-semibold">Upload PDF</h3>
            <span className="ml-auto text-xs rounded bg-slate-100 px-2 py-0.5">.pdf</span>
          </div>

          <div className="text-center p-4 border-2 border-dashed border-slate-200 rounded-lg hover:border-rose-300 transition-colors">
            <UploadArea 
              onFiles={onPDFFiles}
              accept=".pdf"
              multiple={true}
            />
          </div>
          
          {selectedFiles.length > 0 && (
            <div className="mt-3">
              <h3 className="text-xs font-medium mb-1 text-gray-600">Selected files:</h3>
              <ul className="text-xs text-gray-600 space-y-1">
                {selectedFiles.map((file, index) => (
                  <li key={index} className="flex items-center gap-1">
                    <div className="w-1 h-1 bg-gray-400 rounded-full"></div>
                    <span className="truncate">{file.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          
          {pdfUploading && (
            <div className="flex items-center justify-center gap-2 text-rose-600 mt-3">
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-rose-600"></div>
              <span className="text-sm">Processing...</span>
            </div>
          )}
        </div>
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
                  
                  {imp.has_sds_urls && (
                    <button
                      className="chip bg-blue-100 text-blue-800 border-blue-300 hover:bg-blue-200 transition-colors"
                      onClick={() => enhanceWithUrls(imp.id)}
                      disabled={urlEnhancing === imp.id}
                      title="Extract product data from SDS URLs using AI"
                    >
                      {urlEnhancing === imp.id ? (
                        <>
                          <div className="animate-spin rounded-full h-3 w-3 border-b border-blue-600 mr-1"></div>
                          Processing...
                        </>
                      ) : (
                        'Re-write with URL link data'
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
