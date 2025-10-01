import api, { MatchResultItem } from "@/lib/api";
import MatchResults from "@/components/MatchResults";
import { useEffect, useState } from "react";
import { useAI } from "@/contexts/AIContext";
import { useToast } from "@/contexts/ToastContext";

export default function MatchPage({ projectId }: { projectId: number }) {
  const [results, setResults] = useState<MatchResultItem[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("");
  const [thresholds, setThresholds] = useState({ vendor_min: 80, product_min: 75, overall_accept: 85 });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [view, setView] = useState<"table" | "card">("card");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const { startAnalysisForSentToAI, startAutoQueue } = useAI();
  const { showToast } = useToast();

  const run = async () => {
    setRunning(true);
    setProgress(0);
    setStatus("Starting matching...");
    
    try {
      // Start matchning
      const response = await api.post(`/projects/${projectId}/match`, { 
        thresholds: {
          vendor_min: thresholds.vendor_min,
          product_min: thresholds.product_min,
          overall_accept: thresholds.overall_accept,
          weights: {
            vendor: 0.6,
            product: 0.4
          },
          sku_exact_boost: 10,
          numeric_mismatch_penalty: 8
        }
      });
      
      // Poll för progress
      const pollProgress = async () => {
        try {
          const statusRes = await api.get(`/projects/${projectId}/match/status`);
          if (statusRes.data.status === "running") {
            setProgress(statusRes.data.progress || 0);
            setStatus(statusRes.data.message || "Matching products...");
            setTimeout(pollProgress, 1000);
          } else {
            setProgress(100);
            setStatus("Matching complete! AI analysis starting automatically for products with score 70-95...");
            await refresh();
            setRunning(false);
            showToast("Matchning klar! AI-analys startar automatiskt för produkter med score 70-95.", 'success');
          }
        } catch (error) {
          console.error("Progress polling error:", error);
          setStatus("Matching in progress...");
          setTimeout(pollProgress, 2000);
        }
      };
      
      // Start polling efter en kort delay
      setTimeout(pollProgress, 1000);
      
    } catch (error) {
      console.error("Matchning error:", error);
      setStatus("Matching error");
      setRunning(false);
    }
  };

  const refresh = async () => {
    const res = await api.get<MatchResultItem[]>(`/projects/${projectId}/results`);
    setResults(res.data);
  };

  const approveSelected = async () => {
    if (selectedIds.length === 0) {
      showToast("Select at least one row to approve.", 'info');
      return;
    }
    await api.post(`/projects/${projectId}/approve`, { ids: selectedIds });
    await refresh();
    setSelectedIds([]);
  };

  const rejectSelected = async () => {
    if (selectedIds.length === 0) {
      showToast("Select at least one row to reject.", 'info');
      return;
    }
    await api.post(`/projects/${projectId}/reject`, { ids: selectedIds });
    await refresh();
    setSelectedIds([]);
  };

  const sendToAI = async () => {
    if (selectedIds.length === 0) {
      showToast("Select at least one row to send to AI.", 'info');
      return;
    }
    
    // No limit on AI queue size - removed 25 product restriction
    
    await api.post(`/projects/${projectId}/send-to-ai`, { ids: selectedIds });
    await refresh();
    setSelectedIds([]);
    
    // Automatically start AI analysis for all sent_to_ai products
    await startAnalysisForSentToAI(projectId);
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="space-y-4">
      <div className="sticky top-16 z-30 bg-white border-b py-2 flex items-center gap-0.5">
        <div className="flex items-center gap-0.5">
          <span className="text-xs text-gray-600">Vendor ≥</span>
          <input 
            type="number" 
            className="w-10 rounded px-1 py-0.5 text-xs" 
            value={thresholds.vendor_min}
            onChange={e => setThresholds(t => ({ ...t, vendor_min: +e.target.value }))} 
          />
        </div>
        <div className="flex items-center gap-0.5">
          <span className="text-xs text-gray-600">Product ≥</span>
          <input 
            type="number" 
            className="w-10 rounded px-1 py-0.5 text-xs" 
            value={thresholds.product_min}
            onChange={e => setThresholds(t => ({ ...t, product_min: +e.target.value }))} 
          />
        </div>
        <div className="flex items-center gap-0.5">
          <span className="text-xs text-gray-600">Accept ≥</span>
          <input 
            type="number" 
            className="w-10 rounded px-1 py-0.5 text-xs" 
            value={thresholds.overall_accept}
            onChange={e => setThresholds(t => ({ ...t, overall_accept: +e.target.value }))} 
          />
        </div>
        
        <div className="flex items-center gap-0.5">
          <span className="text-xs text-gray-600">Status:</span>
          <select 
            className="rounded border px-1 py-0.5 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All</option>
            <option value="review_required">Review required</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        
        <div className="ml-auto flex items-center gap-0.5">
          <button 
            className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700" 
            onClick={run} 
            disabled={running}
          >
            {running ? "Running..." : "Run matching"}
          </button>
          <button 
            className="rounded-2xl bg-green-100 px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-200" 
            onClick={approveSelected}
          >
            Approve selected
          </button>
          <button 
            className="rounded-2xl bg-red-100 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-200" 
            onClick={rejectSelected}
          >
            Reject selected
          </button>
          <button 
            className="rounded-2xl bg-blue-100 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-200" 
            onClick={sendToAI}
          >
            Send selected to AI
          </button>
        </div>
      </div>
        
        {/* Progress Bar */}
        {running && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm text-gray-600">
              <span>{status}</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all duration-300" 
                style={{ width: `${progress}%` }}
              ></div>
            </div>
          </div>
        )}
        
        <MatchResults 
          results={results} 
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          view={view}
          statusFilter={statusFilter}
        />
    </div>
  );
}
