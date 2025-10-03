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
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(25);
  const { startAutoQueue } = useAI();
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
      
      // Immediately try to refresh results in case matching is very fast
      setTimeout(async () => {
        await refresh();
      }, 1000);
      
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
            
            // Wait a moment for backend to save results
            setTimeout(async () => {
              await refresh();
              setRunning(false);
              showToast("Matchning klar! AI-analys startar automatiskt för produkter med score 70-95.", 'success');
            }, 2000);
          }
        } catch (error) {
          console.error("Progress polling error:", error);
          setStatus("Matching in progress...");
          setTimeout(pollProgress, 2000);
        }
      };
      
      // Start polling efter en kort delay
      setTimeout(pollProgress, 1000);
      
      // Fallback: always refresh after 5 seconds regardless of status
      setTimeout(async () => {
        console.log("Fallback refresh after 5 seconds");
        await refresh();
        setRunning(false);
      }, 5000);
      
    } catch (error) {
      console.error("Matchning error:", error);
      setStatus("Matching error");
      setRunning(false);
    }
  };

  const refresh = async () => {
    try {
      const res = await api.get<MatchResultItem[]>(`/projects/${projectId}/results`);
      console.log("Match results loaded:", res.data.length, "results");
      setResults(res.data);
    } catch (error) {
      console.error("Failed to load match results:", error);
    }
  };

  const approveSelected = async () => {
    if (selectedIds.length === 0) {
      showToast("Välj produkter att godkänna.", 'warning');
      return;
    }
    await api.post(`/projects/${projectId}/approve`, { ids: selectedIds });
    setSelectedIds([]);
    await refresh();
    showToast(`${selectedIds.length} produkter godkända.`, 'success');
  };

  const rejectSelected = async () => {
    if (selectedIds.length === 0) {
      showToast("Välj produkter att avvisa.", 'warning');
      return;
    }
    await api.post(`/projects/${projectId}/reject`, { ids: selectedIds });
    setSelectedIds([]);
    await refresh();
    showToast(`${selectedIds.length} produkter avvisade.`, 'success');
  };

  const sendToAI = async () => {
    if (selectedIds.length === 0) {
      showToast("Välj produkter att skicka till AI.", 'warning');
      return;
    }
    
    // No limit on AI queue size - removed 25 product restriction
    
    await api.post(`/projects/${projectId}/send-to-ai`, { ids: selectedIds });
    await refresh();
    setSelectedIds([]);
    
    // Backend auto_queue_ai_analysis() will handle the AI processing automatically
    // No need to call startAnalysis() here as it would duplicate the AI processing
  };

  useEffect(() => { refresh(); }, []);

  // Pagination logic
  const filteredResults = results.filter(result => {
    if (statusFilter === "all") return true;
    
    // Handle "review_required" as a combination of multiple decision values
    if (statusFilter === "review_required") {
      return result.decision === "pending" || result.decision === "sent_to_ai";
    }
    
    return result.decision === statusFilter;
  });

  const totalPages = Math.ceil(filteredResults.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedResults = filteredResults.slice(startIndex, endIndex);

  // Reset to page 1 when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [statusFilter]);

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
        
        {results.length > 0 && (
          <div className="ml-auto flex items-center gap-0.5">
            <button 
              className="rounded-2xl bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700" 
              onClick={run} 
              disabled={running}
            >
              {running ? "Running..." : "Run matching"}
            </button>
          </div>
        )}
      </div>

      {running && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-blue-900">{status}</span>
            <span className="text-sm text-blue-700">{progress}%</span>
          </div>
          <div className="w-full bg-blue-200 rounded-full h-2">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-300" 
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView("card")}
            className={`px-3 py-1 text-sm rounded ${
              view === "card" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-700"
            }`}
          >
            Card
          </button>
          <button
            onClick={() => setView("table")}
            className={`px-3 py-1 text-sm rounded ${
              view === "table" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-700"
            }`}
          >
            Table
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">
            Showing {startIndex + 1}-{Math.min(endIndex, filteredResults.length)} of {filteredResults.length} results
          </span>
        </div>
      </div>

      {results.length === 0 && !running && (
        <div className="text-center py-12">
          <div className="text-gray-500 text-lg mb-4">
            Inga matchresultat än
          </div>
          <div className="text-gray-400 text-sm mb-6">
            Kör matching först för att se resultat
          </div>
          <button
            onClick={run}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
          >
            Start Matching
          </button>
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-blue-900">
              {selectedIds.length} produkter valda
            </span>
            <div className="flex gap-2">
              <button
                onClick={approveSelected}
                className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
              >
                Godkänn
              </button>
              <button
                onClick={rejectSelected}
                className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
              >
                Avvisa
              </button>
              <button
                onClick={sendToAI}
                className="px-3 py-1 bg-purple-600 text-white text-sm rounded hover:bg-purple-700"
              >
                Skicka till AI
              </button>
            </div>
          </div>
        </div>
      )}

      {results.length > 0 && (
        <MatchResults
          results={paginatedResults}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          view={view}
        />
      )}

      {results.length > 0 && totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
            disabled={currentPage === 1}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          
          <div className="flex gap-1">
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const page = i + 1;
              return (
                <button
                  key={page}
                  onClick={() => setCurrentPage(page)}
                  className={`px-3 py-1 text-sm border rounded ${
                    currentPage === page ? "bg-blue-100 text-blue-700" : ""
                  }`}
                >
                  {page}
                </button>
              );
            })}
          </div>
          
          <button
            onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
            disabled={currentPage === totalPages}
            className="px-3 py-1 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
