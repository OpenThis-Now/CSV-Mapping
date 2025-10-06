import { useEffect, useState } from "react";
import Databases from "./pages/Databases";
import Projects from "./pages/Projects";
import ImportPage from "./pages/Import";
import PDFImportPage from "./pages/PDFImport";
import MatchPage from "./pages/Match";
import AIDeep from "./pages/AIDeep";
import ExportPage from "./pages/Export";
import InfoPage from "./pages/Info";
import RejectedProducts from "./pages/RejectedProducts";
import { AIProvider, useAI } from "./contexts/AIContext";
import { ToastProvider } from "./contexts/ToastContext";
import api from "./lib/api";

type View = "databases" | "projects" | "import" | "match" | "ai" | "export" | "rejected" | "info";

function AppContent() {
  const [view, setView] = useState<View>("projects");
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [hasDatabase, setHasDatabase] = useState<boolean>(false);
  const [hasImports, setHasImports] = useState<boolean>(false);
  const [hasSelectedImport, setHasSelectedImport] = useState<boolean>(false);
  const { isAnalyzing, thinkingStep, isQueueProcessing, queueStatus, checkAndResumeQueue } = useAI();

  // Function to check project status
  const checkProjectStatus = async (projectId: number) => {
    try {
      // Check if project has an active database
      const projectRes = await api.get(`/projects/list`);
      const project = projectRes.data.find((p: any) => p.id === projectId);
      const hasActiveDatabase = project?.active_database_id !== null && project?.active_database_id !== undefined;
      setHasDatabase(hasActiveDatabase);

      if (hasActiveDatabase) {
        // Check if project has imports
        const importsRes = await api.get(`/projects/${projectId}/import`);
        const hasImportFiles = importsRes.data && importsRes.data.length > 0;
        setHasImports(hasImportFiles);

        if (hasImportFiles) {
          // Check if project has a selected import
          const hasActiveImport = project?.active_import_id !== null && project?.active_import_id !== undefined;
          setHasSelectedImport(hasActiveImport);
        } else {
          setHasSelectedImport(false);
        }
      } else {
        setHasImports(false);
        setHasSelectedImport(false);
      }
    } catch (error) {
      console.error("Failed to check project status:", error);
      setHasDatabase(false);
      setHasImports(false);
      setHasSelectedImport(false);
    }
  };

  // Check project status when projectId changes
  useEffect(() => {
    if (projectId) {
      checkProjectStatus(projectId);
    } else {
      setHasDatabase(false);
      setHasImports(false);
      setHasSelectedImport(false);
    }
  }, [projectId]);

  // Check AI status when projectId changes or component mounts
  useEffect(() => {
    if (projectId && checkAndResumeQueue) {
      // Check if AI is currently processing for this project and resume if needed
      checkAndResumeQueue(projectId);
    }
  }, [projectId, checkAndResumeQueue]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-white border-b">
        <div className="max-w-6xl mx-auto flex items-center gap-3 p-3">
          <div className="flex items-center gap-3">
            {/* Mapping Bridge Logo */}
            <img 
              src="/images/mapping-bridge-logo.png" 
              alt="Mapping Bridge Logo" 
              className="h-8 w-auto"
              onError={(e) => {
                // Fallback to text if image fails to load
                const target = e.target as HTMLImageElement;
                target.style.display = 'none';
                const fallback = document.createElement('div');
                fallback.className = 'text-lg font-medium text-gray-700';
                fallback.textContent = 'Mapping Bridge';
                target.parentNode?.insertBefore(fallback, target);
              }}
            />
          </div>
          <nav className="ml-6 flex gap-2">
            <button 
              className={`chip ${view === "projects" ? "bg-blue-100 border-blue-300 text-blue-800" : ""}`}
              onClick={() => setView("projects")}
            >
              Projects
            </button>
            <button 
              className={`chip ${view === "databases" ? "bg-blue-100 border-blue-300 text-blue-800" : ""}`}
              onClick={() => setView("databases")}
            >
              Databases
            </button>
            <button 
              className={`chip ${view === "import" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId || !hasDatabase ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("import")} 
              disabled={!projectId || !hasDatabase}
            >
              Customer Import
            </button>
            <button 
              className={`chip ${view === "match" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId || !hasDatabase || !hasImports || !hasSelectedImport ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("match")} 
              disabled={!projectId || !hasDatabase || !hasImports || !hasSelectedImport}
            >
              Matching
            </button>
            <button 
              className={`chip ${view === "ai" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId || !hasDatabase || !hasImports || !hasSelectedImport ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("ai")} 
              disabled={!projectId || !hasDatabase || !hasImports || !hasSelectedImport}
            >
              AI reviews
            </button>
            <button 
              className={`chip ${view === "export" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId || !hasDatabase || !hasImports || !hasSelectedImport ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("export")} 
              disabled={!projectId || !hasDatabase || !hasImports || !hasSelectedImport}
            >
              Export
            </button>
            <button 
              className={`chip ${view === "rejected" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId || !hasDatabase || !hasImports || !hasSelectedImport ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("rejected")} 
              disabled={!projectId || !hasDatabase || !hasImports || !hasSelectedImport}
            >
              Rejected Products
            </button>
            <button 
              className={`chip ${view === "info" ? "bg-blue-100 border-blue-300 text-blue-800" : ""}`}
              onClick={() => setView("info")}
            >
              Info
            </button>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {(isAnalyzing || isQueueProcessing) && (
              <div className="flex space-x-0.5">
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"></div>
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Project:</span>
              <div className={`px-3 py-2 rounded-lg border text-sm font-semibold ${
                projectName 
                  ? 'bg-gray-200 text-gray-700 border-gray-300' 
                  : 'bg-gray-100 text-gray-500 border-gray-300'
              }`}>
                {projectName ?? "None selected"}
              </div>
            </div>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto p-4 space-y-4">
        {view === "projects" && <Projects onOpen={(id, name) => { 
          setProjectId(id || null); 
          setProjectName(name || null); 
        }} selectedProjectId={projectId} />}
        {view === "databases" && <Databases activeProjectId={projectId} onDatabaseChange={() => projectId && checkProjectStatus(projectId)} />}
        {view === "import" && projectId && <ImportPage projectId={projectId} onImportChange={() => checkProjectStatus(projectId)} />}
        {view === "match" && projectId && <MatchPage projectId={projectId} />}
        {view === "ai" && projectId && <AIDeep projectId={projectId} />}
        {view === "export" && projectId && <ExportPage projectId={projectId} />}
        {view === "rejected" && projectId && <RejectedProducts projectId={projectId} />}
        {view === "info" && <InfoPage />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AIProvider>
        <AppContent />
      </AIProvider>
    </ToastProvider>
  );
}