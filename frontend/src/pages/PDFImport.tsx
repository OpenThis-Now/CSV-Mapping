import { useState, useEffect } from "react";
import { useToast } from "@/contexts/ToastContext";
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
  const [imports, setImports] = useState<ImportFile[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [selectedImports, setSelectedImports] = useState<Set<number>>(new Set());
  const [combining, setCombining] = useState(false);
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


  const toggleImport = async (importId: number) => {
    try {
      const isCurrentlySelected = project?.active_import_id === importId;
      const newImportId = isCurrentlySelected ? null : importId;
      
      // console.log("PDFImport.tsx: Toggling import:", { projectId, importId, newImportId, currentProject: project });
      
      const response = await api.patch(`/projects/${projectId}`, { active_import_id: newImportId });
      // console.log("PDFImport.tsx: PATCH response:", response.data);
      
      await refreshProject();
    } catch (error) {
      console.error("Failed to toggle import:", error);
      showToast("Failed to toggle import selection", 'error');
    }
  };

  const toggleImportSelection = (importId: number) => {
    const newSelected = new Set(selectedImports);
    if (newSelected.has(importId)) {
      newSelected.delete(importId);
    } else {
      newSelected.add(importId);
    }
    setSelectedImports(newSelected);
  };

  const combineSelectedImports = async () => {
    if (selectedImports.size === 0) {
      showToast("Välj minst en fil att kombinera", 'error');
      return;
    }

    setCombining(true);
    try {
      const importIds = Array.from(selectedImports);
      const response = await api.post(`/projects/${projectId}/combine-imports`, {
        import_ids: importIds
      });
      
      showToast(`Kombinerade ${importIds.length} filer till en ny import`, 'success');
      setSelectedImports(new Set());
      await refreshImports();
      await refreshProject();
    } catch (error: any) {
      console.error("Failed to combine imports:", error);
      const errorMessage = error.response?.data?.detail || "Kombinering misslyckades";
      showToast(`Kombinering misslyckades: ${errorMessage}`, 'error');
    } finally {
      setCombining(false);
    }
  };

  const startMatchingOnCombined = async () => {
    if (selectedImports.size === 0) {
      showToast("Välj minst en fil att matcha", 'error');
      return;
    }

    if (!project?.active_database_id) {
      showToast("Välj en databas först", 'error');
      return;
    }

    setCombining(true);
    try {
      const importIds = Array.from(selectedImports);
      
      // Kombinera filerna först
      const combineResponse = await api.post(`/projects/${projectId}/combine-imports`, {
        import_ids: importIds
      });
      
      // Sätt den kombinerade filen som aktiv
      await api.patch(`/projects/${projectId}`, { 
        active_import_id: combineResponse.data.import_file_id 
      });
      
      // Starta matchning
      const matchResponse = await api.post(`/projects/${projectId}/match`, {
        thresholds: {
          vendor_min: 80,
          product_min: 75,
          overall_accept: 85,
          weights: { vendor: 0.6, product: 0.4 },
          sku_exact_boost: 10,
          numeric_mismatch_penalty: 8
        }
      });
      
      showToast(`Kombinerade ${importIds.length} filer och startade matchning`, 'success');
      setSelectedImports(new Set());
      await refreshImports();
      await refreshProject();
      
      // Navigera till match-sidan
      window.location.href = `/projects/${projectId}/match`;
      
    } catch (error: any) {
      console.error("Failed to combine and match:", error);
      const errorMessage = error.response?.data?.detail || "Kombinering/matchning misslyckades";
      showToast(`Kombinering/matchning misslyckades: ${errorMessage}`, 'error');
    } finally {
      setCombining(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Merge Files</h1>
        <div className="text-sm text-gray-600">
          Project: {project?.name || 'Loading...'}
        </div>
      </div>

      {/* Info Section */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 mb-2">How to Merge Files</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Upload your files using the "Customer Import" page</li>
          <li>• Select multiple uploaded files with checkboxes below</li>
          <li>• Click "Kombinera X filer" to merge them into one file</li>
          <li>• Or click "Kombinera & Matcha X filer" to merge and start matching directly</li>
        </ul>
      </div>

      {/* Import History */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Uploaded Files</h2>
          {selectedImports.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">
                {selectedImports.size} filer valda
              </span>
              <button
                onClick={combineSelectedImports}
                disabled={combining}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {combining ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white inline-block mr-2"></div>
                    Kombinerar...
                  </>
                ) : (
                  `Kombinera ${selectedImports.size} filer`
                )}
              </button>
              {project?.active_database_id && (
                <button
                  onClick={startMatchingOnCombined}
                  disabled={combining}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {combining ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white inline-block mr-2"></div>
                      Bearbetar...
                    </>
                  ) : (
                    `Kombinera & Matcha ${selectedImports.size} filer`
                  )}
                </button>
              )}
            </div>
          )}
        </div>
        
        {imports.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No files uploaded yet. Go to "Customer Import" to upload CSV or PDF files.
          </div>
        ) : (
          <div className="space-y-2">
            {imports.map((imp) => (
              <div 
                key={imp.id} 
                className={`p-4 border rounded-lg transition-colors ${
                  project?.active_import_id === imp.id 
                    ? 'border-blue-500 bg-blue-50' 
                    : selectedImports.has(imp.id)
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={selectedImports.has(imp.id)}
                      onChange={() => toggleImportSelection(imp.id)}
                      className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                    />
                    <div 
                      className="flex-1 cursor-pointer"
                      onClick={() => toggleImport(imp.id)}
                    >
                      <div className="font-medium">{imp.original_name}</div>
                      <div className="text-sm text-gray-600">
                        {imp.row_count} products extracted • {new Date(imp.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {project?.active_import_id === imp.id && (
                      <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
                        Active
                      </span>
                    )}
                    {selectedImports.has(imp.id) && (
                      <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                        Selected
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
      <div className="bg-green-50 border border-green-200 rounded-lg p-4">
        <h3 className="font-semibold text-green-900 mb-2">Merge Instructions</h3>
        <ul className="text-sm text-green-800 space-y-1">
          <li>• <strong>Step 1:</strong> Upload files using "Customer Import" (CSV or PDF)</li>
          <li>• <strong>Step 2:</strong> Select multiple files with checkboxes above</li>
          <li>• <strong>Step 3:</strong> Click "Kombinera X filer" to merge into one file</li>
          <li>• <strong>Step 4:</strong> Or use "Kombinera & Matcha X filer" for direct matching</li>
          <li>• Merged files include source tracking (_source_file, _source_id columns)</li>
        </ul>
      </div>
    </div>
  );
}
