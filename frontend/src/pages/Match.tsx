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
    setStatus(results.length > 0 ? "Matching new products..." : "Starting matching...");
    
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
        },
        match_new_only: results.length > 0  // Match only new products if we have existing results
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
              const message = results.length > 0 
                ? "New products matched! AI analysis starting automatically for products with score 70-95." 
                : "Matching complete! AI analysis starting automatically for products with score 70-95.";
              showToast(message, 'success');
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
      console.log("Match results data:", res.data);
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

  useEffect(() => { 
    console.log("Match page loaded, refreshing results...");
    refresh(); 
  }, []);

  // Pagination logic
  const filteredResults = results
    .filter(result => {
      if (statusFilter === "all") return true;
      
      // Handle "review_required" as a combination of multiple decision values
      if (statusFilter === "review_required") {
        const matches = result.decision === "pending" || result.decision === "sent_to_ai";
        console.log(`Filtering result with decision "${result.decision}": ${matches}`);
        return matches;
      }
      
      // Handle "approved" - include both manual and auto approvals
      if (statusFilter === "approved") {
        const matches = result.decision === "approved" || 
                       result.decision === "auto_approved" || 
                       result.decision === "ai_auto_approved";
        console.log(`Filtering result with decision "${result.decision}" for approved: ${matches}`);
        return matches;
      }
      
      // Handle "rejected" - include both manual and auto rejections
      if (statusFilter === "rejected") {
        const matches = result.decision === "rejected" || result.decision === "auto_rejected";
        console.log(`Filtering result with decision "${result.decision}" for rejected: ${matches}`);
        return matches;
      }
      
      const matches = result.decision === statusFilter;
      console.log(`Filtering result with decision "${result.decision}" against filter "${statusFilter}": ${matches}`);
      return matches;
    })
  .sort((a, b) => {
    // Sort by decision first (pending first), then by customer_row_index, then by id
    const decisionOrder = { pending: 0, sent_to_ai: 1, auto_rejected: 2, auto_approved: 3, approved: 4, rejected: 5 };
    const aOrder = decisionOrder[a.decision as keyof typeof decisionOrder] ?? 999;
    const bOrder = decisionOrder[b.decision as keyof typeof decisionOrder] ?? 999;
    
    if (aOrder !== bOrder) {
      return aOrder - bOrder;
    }
    
    // Within same decision, sort by customer_row_index
    if (a.customer_row_index !== b.customer_row_index) {
      return a.customer_row_index - b.customer_row_index;
    }
    
    return a.id - b.id;
  });

  const totalPages = Math.ceil(filteredResults.length / itemsPerPage);
  const safeCurrentPage = Math.max(1, currentPage);
  const startIndex = (safeCurrentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedResults = filteredResults.slice(startIndex, endIndex);
  
  // Debug pagination
  console.log("=== PAGINATION DEBUG ===");
  console.log("Results count:", results.length);
  console.log("Filtered results count:", filteredResults.length);
  console.log("Current page:", currentPage);
  console.log("Items per page:", itemsPerPage);
  console.log("Status filter:", statusFilter);
  
  // Debug sorting
  console.log("=== SORTING DEBUG ===");
  console.log("First 5 results from backend:", results.slice(0, 5).map(r => ({ id: r.id, customer_row_index: r.customer_row_index, decision: r.decision })));
  console.log("First 5 filtered results:", filteredResults.slice(0, 5).map(r => ({ id: r.id, customer_row_index: r.customer_row_index, decision: r.decision })));
  
  // Debug pending products specifically
  const pendingProducts = results.filter(r => r.decision === "pending");
  const pendingOnCurrentPage = paginatedResults.filter(r => r.decision === "pending");
  
  console.log("=== PENDING PRODUCTS DEBUG ===");
  console.log("All pending products:", pendingProducts.map(r => ({ id: r.id, customer_row_index: r.customer_row_index, decision: r.decision })));
  console.log("Pending on current page:", pendingOnCurrentPage.map(r => ({ id: r.id, customer_row_index: r.customer_row_index, decision: r.decision })));
  console.log("Total pending count:", pendingProducts.length);
  console.log("Pending on current page count:", pendingOnCurrentPage.length);
  
  // Debug all decisions
  console.log("=== DECISIONS DEBUG ===");
  const decisionCounts = results.reduce((acc, r) => {
    acc[r.decision] = (acc[r.decision] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  console.log("Decision counts:", decisionCounts);

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
              className="rounded-2xl bg-blue-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-600" 
            onClick={run} 
            disabled={running}
          >
              {running ? "Running..." : "Match new products"}
          </button>
          </div>
        )}
      </div>

      {selectedIds.length > 0 && (
        <div className="sticky top-16 z-20 bg-blue-50 border border-blue-200 rounded-lg p-3 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-blue-900">
              {selectedIds.length} product{selectedIds.length !== 1 ? 's' : ''} selected
            </span>
            <div className="flex gap-2">
          <button 
            onClick={approveSelected}
                className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
          >
                Approve
          </button>
          <button 
            onClick={rejectSelected}
                className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
          >
                Reject
          </button>
          <button 
            onClick={sendToAI}
                className="px-3 py-1 bg-purple-600 text-white text-sm rounded hover:bg-purple-700"
          >
                Send to AI
          </button>
        </div>
      </div>
        </div>
      )}
        
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


      {results.length === 0 && !running && (
        <div className="text-center py-12">
          <div className="text-gray-500 text-lg mb-4">
            No matches yet
          </div>
          <div className="text-gray-400 text-sm mb-6">
            Run matching to see results
          </div>
          <div className="flex justify-center">
            <button
              onClick={run}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            >
              Start Matching
            </button>
            </div>
          </div>
        )}
        

      {results.length > 0 && (
        <>
          {console.log("Rendering MatchResults with:", {
            paginatedResultsLength: paginatedResults.length,
            paginatedResultsData: paginatedResults,
            view: view
          })}
        <MatchResults 
            results={paginatedResults}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          view={view}
          statusFilter={statusFilter}
            totalResults={results.length}
            filteredResults={filteredResults.length}
            startIndex={startIndex}
            endIndex={endIndex}
          />
        </>
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
