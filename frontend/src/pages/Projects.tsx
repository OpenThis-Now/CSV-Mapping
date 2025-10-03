import { useEffect, useState } from "react";
import api, { Project, DatabaseListItem } from "@/lib/api";
import DetailedProgressBar from "@/components/DetailedProgressBar";

type ProjectStats = {
  total_products: number;
  status_breakdown: {
    pending: number;
    auto_approved: number;
    approved: number;
    not_approved: number; // Maps to rejected + auto_rejected from backend
    sent_to_ai: number;
    ai_auto_approved: number;
    worklist: number;
  };
};

export default function Projects({ onOpen, selectedProjectId }: { onOpen: (id: number | null, name: string | null) => void; selectedProjectId?: number | null }) {
  const [name, setName] = useState("");
  const [list, setList] = useState<Project[]>([]);
  const [databases, setDatabases] = useState<DatabaseListItem[]>([]);
  const [projectStats, setProjectStats] = useState<Record<number, ProjectStats>>({});
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const [editingProject, setEditingProject] = useState<number | null>(null);
  const [editName, setEditName] = useState<string>("");

  const refresh = async () => {
    try {
      console.log("Projects.tsx: Refreshing project list...");
      const [projectsRes, databasesRes] = await Promise.all([
        api.get<Project[]>("/projects/list"),
        api.get<DatabaseListItem[]>("/databases")
      ]);
      
      console.log("Projects.tsx: Received project data:", projectsRes.data);
      console.log("Projects.tsx: Number of projects received:", projectsRes.data.length);
      console.log("Projects.tsx: Project names:", projectsRes.data.map(p => p.name));
      
      setList(projectsRes.data);
      setDatabases(databasesRes.data);
      
      // Fetch stats for each project
      const statsPromises = projectsRes.data.map(async (project) => {
        try {
          const statsRes = await api.get<ProjectStats>(`/projects/${project.id}/stats`);
          return { projectId: project.id, stats: statsRes.data };
        } catch (error) {
          console.error(`Failed to fetch stats for project ${project.id}:`, error);
          return { projectId: project.id, stats: null };
        }
      });
      
      const statsResults = await Promise.all(statsPromises);
      const statsMap: Record<number, ProjectStats> = {};
      statsResults.forEach(({ projectId, stats }) => {
        if (stats) {
          statsMap[projectId] = stats;
        }
      });
      setProjectStats(statsMap);
      
      setLastRefresh(Date.now());
    } catch (e) {
      console.error("Projects.tsx: Error refreshing:", e);
    }
  };

  useEffect(() => { refresh(); }, []);
  
  // Helper function to get database name by ID
  const getDatabaseName = (databaseId: number | null): string => {
    if (!databaseId) return "-";
    const database = databases.find(db => db.id === databaseId);
    return database ? database.name : `DB ${databaseId}`;
  };

  // Helper function to format status counts
  const formatStatusCounts = (stats: ProjectStats | undefined) => {
    if (!stats || stats.total_products === 0) {
      return {
        total: 0,
        matched: 0,
        actionRequired: 0,
        notAvailable: 0
      };
    }
    
    const breakdown = stats.status_breakdown;
    
    return {
      total: stats.total_products,
      matched: breakdown.approved + breakdown.auto_approved + breakdown.ai_auto_approved,
      actionRequired: breakdown.pending + breakdown.sent_to_ai,
      notAvailable: breakdown.not_approved
    };
  };
  
  // Refresh when the page becomes visible or when user clicks on it
  useEffect(() => {
    const handleFocus = () => {
      console.log("Projects.tsx: Window focus detected, refreshing...");
      refresh();
    };
    
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        console.log("Projects.tsx: Page visible, refreshing...");
        refresh();
      }
    };
    
    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      window.removeEventListener('focus', handleFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);
  

  const create = async () => {
    if (!name.trim()) return;
    const res = await api.post<Project>("/projects", { name });
    setName("");
    onOpen(res.data.id, res.data.name);
    refresh();
  };

  const deleteProject = async (projectId: number) => {
    if (!confirm("Are you sure you want to delete this project? This cannot be undone and all related data will be deleted.")) {
      return;
    }
    
    try {
      await api.delete(`/projects/${projectId}`);
      await refresh();
    } catch (error) {
      console.error("Failed to delete project:", error);
      alert("Could not delete project. Please try again.");
    }
  };

  const startEdit = (project: Project) => {
    setEditingProject(project.id);
    setEditName(project.name);
  };

  const cancelEdit = () => {
    setEditingProject(null);
    setEditName("");
  };

  const saveEdit = async (projectId: number) => {
    if (!editName.trim()) {
      alert("Project name cannot be empty");
      return;
    }
    
    try {
      await api.patch(`/projects/${projectId}`, { name: editName.trim() });
      setEditingProject(null);
      setEditName("");
      await refresh();
    } catch (error) {
      console.error("Failed to update project name:", error);
      alert("Could not update project name. Please try again.");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
      </div>
      <div className="card flex gap-2">
        <input className="border rounded-xl px-3 py-2 flex-1" placeholder="Project name" value={name} onChange={e => setName(e.target.value)} />
        <button 
          className="flex items-center gap-1 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded border border-blue-600 hover:border-blue-700 transition-colors"
          onClick={create}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
          </svg>
          Create
        </button>
      </div>
      <div className="grid gap-2">
        {list.map(p => {
          const counts = formatStatusCounts(projectStats[p.id]);
          const pctCompleted = counts.total > 0 ? ((counts.matched + (projectStats[p.id]?.status_breakdown.not_approved || 0) + (projectStats[p.id]?.status_breakdown.worklist || 0)) / counts.total) * 100 : 0;
          
          // Debug logging
          const progressBarData = {
            total: counts.total,
            approved: (projectStats[p.id]?.status_breakdown.approved || 0) + 
                     (projectStats[p.id]?.status_breakdown.auto_approved || 0) + 
                     (projectStats[p.id]?.status_breakdown.ai_auto_approved || 0),
            worklist: projectStats[p.id]?.status_breakdown.worklist || 0,
            rejected: projectStats[p.id]?.status_breakdown.not_approved || 0,
            pending: counts.actionRequired
          };
          
          console.log(`Project ${p.id} (${p.name}):`, {
            projectStats: projectStats[p.id],
            counts,
            hasStats: !!projectStats[p.id],
            progressBarData,
            breakdown: projectStats[p.id]?.status_breakdown
          });
          

          const Pill = ({ children }: { children: React.ReactNode }) => (
            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
              {children}
            </span>
          );

          return (
            <div key={p.id} className="card shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  {editingProject === p.id ? (
                    <div className="flex items-center gap-2 mb-1">
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="px-2 py-1 border border-gray-300 rounded text-lg font-medium"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveEdit(p.id);
                          if (e.key === 'Escape') cancelEdit();
                        }}
                      />
                      <button
                        onClick={() => saveEdit(p.id)}
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
                    <div className="font-medium text-lg mb-1 flex items-center gap-2">
                      {p.name}
                      <button
                        onClick={() => startEdit(p)}
                        className="text-gray-400 hover:text-gray-600 text-sm p-1"
                        title="Edit project name"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                    </div>
                  )}
                  <div className="text-xs text-gray-500 mb-3">Status: {p.status} · Active DB: {getDatabaseName(p.active_database_id ?? null)}</div>
                  
                  <div className="space-y-4">
                    {/* Header with total */}
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">Products</span>
                      <Pill>{counts.total} total</Pill>
                    </div>

                    {/* Detailed Progress bar - always show */}
                    <DetailedProgressBar
                      total={counts.total}
                      approved={(projectStats[p.id]?.status_breakdown.approved || 0) + 
                               (projectStats[p.id]?.status_breakdown.auto_approved || 0) + 
                               (projectStats[p.id]?.status_breakdown.ai_auto_approved || 0)}
                      worklist={projectStats[p.id]?.status_breakdown.worklist || 0}
                      rejected={projectStats[p.id]?.status_breakdown.not_approved || 0}
                      pending={counts.actionRequired}
                    />
                  </div>
                </div>
                
                {/* Action buttons */}
                <div className="flex flex-col gap-2 ml-4">
                  {selectedProjectId === p.id ? (
                    <button 
                      className="chip bg-green-100 text-green-800 border-green-300 font-semibold hover:bg-green-200" 
                      onClick={() => onOpen(null, "")}
                    >
                      Selected ✓
                    </button>
                  ) : (
                    <button className="chip" onClick={() => onOpen(p.id, p.name)}>Open</button>
                  )}
                  <button 
                    className="flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:text-red-600 hover:bg-red-50 rounded border border-gray-200 hover:border-red-200 transition-colors"
                    onClick={() => deleteProject(p.id)}
                    title="Delete project"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    Delete
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
