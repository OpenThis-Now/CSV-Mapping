import { useEffect, useState } from "react";
import api, { Project, DatabaseListItem } from "@/lib/api";

type ProjectStats = {
  total_products: number;
  status_breakdown: {
    pending: number;
    auto_approved: number;
    approved: number;
    not_approved: number;
    sent_to_ai: number;
    ai_auto_approved: number;
  };
};

export default function Projects({ onOpen, selectedProjectId }: { onOpen: (id: number | null, name: string | null) => void; selectedProjectId?: number | null }) {
  const [name, setName] = useState("");
  const [list, setList] = useState<Project[]>([]);
  const [databases, setDatabases] = useState<DatabaseListItem[]>([]);
  const [projectStats, setProjectStats] = useState<Record<number, ProjectStats>>({});
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
      </div>
      <div className="card flex gap-2">
        <input className="border rounded-xl px-3 py-2 flex-1" placeholder="Project name" value={name} onChange={e => setName(e.target.value)} />
        <button className="btn" onClick={create}>Create</button>
      </div>
      <div className="grid gap-2">
        {list.map(p => {
          const counts = formatStatusCounts(projectStats[p.id]);
          return (
            <div key={p.id} className="card flex items-center justify-between">
              <div className="flex-1">
                <div className="font-medium">{p.name}</div>
                <div className="text-xs opacity-70 mb-2">Status: {p.status} · Active DB: {getDatabaseName(p.active_database_id)}</div>
                
                {counts.total > 0 ? (
                  <div className="space-y-1">
                    <div className="font-semibold text-base text-gray-900">{counts.total} products</div>
                    <div className="flex gap-3 text-xs text-gray-600">
                      <span>{counts.matched} Matched</span>
                      <span>{counts.actionRequired} Action required</span>
                      <span>{counts.notAvailable} Not available in database</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">No products</div>
                )}
                </div>
              <div className="flex gap-2">
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
                <button className="chip bg-red-100 text-red-700 hover:bg-red-200" onClick={() => deleteProject(p.id)}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
