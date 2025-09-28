import { useEffect, useState } from "react";
import api, { Project } from "@/lib/api";

export default function Projects({ onOpen, selectedProjectId }: { onOpen: (id: number, name: string) => void; selectedProjectId?: number | null }) {
  const [name, setName] = useState("");
  const [list, setList] = useState<Project[]>([]);

  const refresh = async () => {
    try {
      const r = await api.get<Project[]>("/projects/list");
      setList(r.data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { refresh(); }, []);

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
      <h1 className="text-xl font-semibold">Projects</h1>
      <div className="card flex gap-2">
        <input className="border rounded-xl px-3 py-2 flex-1" placeholder="Project name" value={name} onChange={e => setName(e.target.value)} />
        <button className="btn" onClick={create}>Create</button>
      </div>
      <div className="grid gap-2">
        {list.map(p => (
          <div key={p.id} className="card flex items-center justify-between">
            <div>
              <div className="font-medium">{p.name}</div>
              <div className="text-xs opacity-70">Status: {p.status} · Active DB: {p.active_database_id ?? "-"}</div>
            </div>
            <div className="flex gap-2">
              {selectedProjectId === p.id ? (
                <button className="chip bg-green-100 text-green-800 border-green-300 font-semibold" disabled>
                  Selected
                </button>
              ) : (
                <button className="chip" onClick={() => onOpen(p.id, p.name)}>Open</button>
              )}
              <button className="chip bg-red-100 text-red-700 hover:bg-red-200" onClick={() => deleteProject(p.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
