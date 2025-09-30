import { useState, useEffect } from "react";
import { useToast } from "@/contexts/ToastContext";
import UploadArea from "@/components/UploadArea";
import api from "@/lib/api";

type ImportFile = {
  id: number;
  filename: string;
  original_name: string;
  row_count: number;
  created_at: string;
};

type Project = {
  id: number;
  name: string;
  status: string;
  active_database_id?: number | null;
  active_import_id?: number | null;
};

export default function PDFImportPage({ projectId }: { projectId: number }) {
  const [status, setStatus] = useState<string | null>(null);
  const [last, setLast] = useState<any | null>(null);
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const { showToast } = useToast();

  const refreshImports = async () => {
    try {
      const res = await api.get<ImportFile[]>(`/projects/${projectId}/pdf-import`);
      setImports(res.data);
    } catch (error) {
      console.error("Failed to load PDF imports:", error);
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

  const onPDFFiles = async (files: File[]) => {
    setSelectedFiles(files);
    setUploading(true);
    
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
      setUploading(false);
      setSelectedFiles([]);
    }
  };

  const toggleImport = async (importId: number) => {
    try {
      const isCurrentlySelected = project?.active_import_id === importId;
      const newImportId = isCurrentlySelected ? null : importId;
      
      console.log("PDFImport.tsx: Toggling import:", { projectId, importId, newImportId, currentProject: project });
      
      const response = await api.patch(`/projects/${projectId}`, { active_import_id: newImportId });
      console.log("PDFImport.tsx: PATCH response:", response.data);
      
      await refreshProject();
    } catch (error) {
      console.error("Failed to toggle import:", error);
      showToast("Failed to toggle import selection", 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">PDF Import</h1>
        <div className="text-sm text-gray-600">
          Project: {project?.name || 'Loading...'}
        </div>
      </div>

      {/* Upload Section */}
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
        
        {uploading && (
          <div className="flex items-center gap-2 text-blue-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
            Processing PDF files with AI...
          </div>
        )}
        
        {status && (
          <div className={`p-3 rounded text-sm ${
            status.includes('Failed') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
          }`}>
            {status}
          </div>
        )}
      </div>

      {/* Import History */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">PDF Import History</h2>
        
        {imports.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No PDF imports yet. Upload some PDF files to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {imports.map((imp) => (
              <div 
                key={imp.id} 
                className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                  project?.active_import_id === imp.id 
                    ? 'border-blue-500 bg-blue-50' 
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => toggleImport(imp.id)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{imp.original_name}</div>
                    <div className="text-sm text-gray-600">
                      {imp.row_count} products extracted • {new Date(imp.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {project?.active_import_id === imp.id && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
                        Active
                      </span>
                    )}
                    <div className="text-sm text-gray-500">
                      {imp.filename}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 mb-2">How PDF Import Works</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Upload multiple PDF files (SDS documents) at once</li>
          <li>• AI reads the first 3 pages of each PDF</li>
          <li>• Extracts: Product name, Article number, Company name, Market, Language</li>
          <li>• Creates a CSV file that can be used for matching</li>
          <li>• Failed PDFs are included as empty rows with filename</li>
        </ul>
      </div>
    </div>
  );
}
