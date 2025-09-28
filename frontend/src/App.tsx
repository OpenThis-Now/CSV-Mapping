import { useEffect, useState } from "react";
import Databases from "./pages/Databases";
import Projects from "./pages/Projects";
import ImportPage from "./pages/Import";
import MatchPage from "./pages/Match";
import AIDeep from "./pages/AIDeep";
import ExportPage from "./pages/Export";
import InfoPage from "./pages/Info";
import { AIProvider, useAI } from "./contexts/AIContext";
import { ToastProvider } from "./contexts/ToastContext";

type View = "databases" | "projects" | "import" | "match" | "ai" | "export" | "info";

function AppContent() {
  const [view, setView] = useState<View>("projects");
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const { isAnalyzing, thinkingStep } = useAI();

  useEffect(() => {}, []);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-white border-b">
        <div className="max-w-6xl mx-auto flex items-center gap-3 p-3">
          <div className="text-xl font-semibold">CSV Match Assistant</div>
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
              className={`chip ${view === "import" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("import")} 
              disabled={!projectId}
            >
              Import
            </button>
            <button 
              className={`chip ${view === "match" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("match")} 
              disabled={!projectId}
            >
              Matching
            </button>
            <button 
              className={`chip ${view === "ai" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("ai")} 
              disabled={!projectId}
            >
              AI Deep Analysis
            </button>
            <button 
              className={`chip ${view === "export" ? "bg-blue-100 border-blue-300 text-blue-800" : ""} ${!projectId ? "opacity-50 cursor-not-allowed" : ""}`}
              onClick={() => setView("export")} 
              disabled={!projectId}
            >
              Export
            </button>
            <button 
              className={`chip ${view === "info" ? "bg-blue-100 border-blue-300 text-blue-800" : ""}`}
              onClick={() => setView("info")}
            >
              Info
            </button>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {isAnalyzing && (
              <div className="flex items-center gap-2 bg-blue-50 px-3 py-1 rounded-full">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.1s'}}></div>
                  <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></div>
                </div>
                <span className="text-sm text-blue-800 font-medium">AI analyzing...</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Project:</span>
              <div className={`px-3 py-2 rounded-lg border text-sm font-semibold ${
                projectName 
                  ? 'bg-green-100 text-green-800 border-green-300' 
                  : 'bg-gray-100 text-gray-500 border-gray-300'
              }`}>
                {projectName ?? "None selected"}
              </div>
            </div>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto p-4 space-y-4">
        {view === "projects" && <Projects onOpen={(id, name) => { setProjectId(id); setProjectName(name); }} selectedProjectId={projectId} />}
        {view === "databases" && <Databases activeProjectId={projectId} />}
        {view === "import" && projectId && <ImportPage projectId={projectId} />}
        {view === "match" && projectId && <MatchPage projectId={projectId} />}
        {view === "ai" && projectId && <AIDeep projectId={projectId} />}
        {view === "export" && projectId && <ExportPage projectId={projectId} />}
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
