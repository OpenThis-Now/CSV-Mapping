import React, { useMemo, useState } from "react";
import { MatchResultItem } from "@/lib/api";
import CountryFlag from "./CountryFlag";
import { Send } from "lucide-react";

interface MatchResultsProps {
  results: MatchResultItem[];
  selectedIds: number[];
  onSelectionChange: (ids: number[]) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onSendToAI: (id: number) => void;
  view: "table" | "card";
  statusFilter: string;
  totalResults?: number;
  filteredResults?: number;
  startIndex?: number;
  endIndex?: number;
}

function Badge({ children, tone = "gray" }: { children: React.ReactNode; tone?: "gray" | "green" | "yellow" | "red" | "blue" }) {
  const tones: Record<string, string> = {
    gray: "bg-gray-100 text-gray-700 border-gray-200",
    green: "bg-green-50 text-green-700 border-green-200",
    yellow: "bg-yellow-50 text-yellow-700 border-yellow-200",
    red: "bg-red-50 text-red-700 border-red-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

function TripleCell({ title, vendor, sku, market, legislation, language }: { title: string; vendor: string; sku: string; market?: string; legislation?: string; language?: string }) {
  const hasVendor = vendor && vendor !== "-" && vendor.trim() !== "";
  const hasSku = sku && sku !== "-" && sku.trim() !== "";
  const hasTitle = title && title !== "-" && title.trim() !== "";
  
  return (
    <div className="flex flex-col gap-0.5 leading-tight">
      <div className={`text-base font-semibold tracking-tight ${!hasTitle ? 'text-gray-400 italic' : ''}`}>
        {hasTitle ? title : "Missing product name"}
      </div>
      <div className={`text-sm ${hasVendor ? 'text-gray-600' : 'text-red-400 italic'}`}>
        {hasVendor ? vendor : "Missing supplier"}
      </div>
      <div className={`text-xs ${hasSku ? 'text-gray-500' : 'text-red-400 italic'}`}>
        {hasSku ? sku : "Missing art.no"}
      </div>
      {(market || language) && (
        <div className="text-xs text-gray-500">
          <span className="flex items-center gap-1">
            {market && (
              <>
                <CountryFlag market={market} />
                {market}
              </>
            )}
            {market && language && " | "}
            {language && <span>{language}</span>}
          </span>
        </div>
      )}
      {legislation && (
        <div className="text-xs text-blue-600">
          <span>Legislation: {legislation}</span>
        </div>
      )}
    </div>
  );
}

function TableView({ results, selectedIds, onSelectionChange }: { results: MatchResultItem[]; selectedIds: number[]; onSelectionChange: (ids: number[]) => void }) {
  // Sort results according to priority:
  // 1. Lowest score first (highest priority)
  // 2. Rejected second
  // 3. Auto approved third
  // 4. Approved last (lowest priority)
  const sortedResults = [...results].sort((a, b) => {
    // First sort by decision priority
    const decisionPriority = (decision: string) => {
      switch (decision) {
        case "approved": return 5; // Lowest priority
        case "ai_auto_approved": return 4; // Fourth priority
        case "rejected": return 2; // Second priority
        case "auto_rejected": return 2; // Second priority (same as rejected)
        case "auto_approved": return 3; // Third priority
        default: return 1; // Highest priority (pending, sent_to_ai)
      }
    };
    
    const aPriority = decisionPriority(a.decision);
    const bPriority = decisionPriority(b.decision);
    
    if (aPriority !== bPriority) {
      return aPriority - bPriority;
    }
    
    // If same decision priority, sort by score (lowest first)
    return a.overall_score - b.overall_score;
  });

  // Debug: Log the first result to see what data we're getting
  if (results.length > 0) {
    console.log("First result:", results[0]);
    console.log("Customer preview:", results[0].customer_preview);
    console.log("DB preview:", results[0].db_preview);
  }

  return (
    <div className="overflow-hidden rounded-2xl border bg-white">
      <table className="min-w-full table-fixed">
        <thead>
          <tr className="bg-gray-50">
            <th className="w-10 px-3 py-3"></th>
            <th className="px-3 py-3 text-left text-sm font-semibold text-gray-700">Customer data</th>
            <th className="px-3 py-3 text-left text-sm font-semibold text-gray-700">Database data</th>
            <th className="w-40 px-3 py-3 text-left text-sm font-semibold text-gray-700">Status</th>
            <th className="w-24 px-3 py-3 text-left text-sm font-semibold text-gray-700">Score</th>
            <th className="w-24 px-3 py-3 text-left text-sm font-semibold text-gray-700">AI-score</th>
            <th className="w-72 px-3 py-3 text-left text-sm font-semibold text-gray-700">Reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sortedResults.map((r) => (
            <tr key={r.id} className="hover:bg-gray-50/60">
              <td className="px-3 py-4 align-top">
                <input 
                  type="checkbox" 
                  className="h-4 w-4 rounded border-gray-300" 
                  checked={selectedIds.includes(r.id)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      onSelectionChange([...selectedIds, r.id]);
                    } else {
                      onSelectionChange(selectedIds.filter(id => id !== r.id));
                    }
                  }}
                />
              </td>
              <td className="px-3 py-4 align-top">
                <TripleCell 
                  title={r.customer_preview["Product"] || r.customer_preview["Produkt"] || "-"} 
                  vendor={r.customer_preview["Supplier"] || r.customer_preview["Leverantör"] || "-"} 
                  sku={r.customer_preview["Art.no"] || r.customer_preview["Artikelnummer"] || "-"} 
                  market={r.customer_preview["Market"] || r.customer_preview["Marknad"] || ""}
                  language={r.customer_preview["Language"] || r.customer_preview["Språk"] || ""}
                />
              </td>
              <td className="px-3 py-4 align-top">
                {r.overall_score < 15 ? (
                  <div className="text-sm text-gray-500 italic">
                    Not on market & language
                  </div>
                ) : (
                  <TripleCell 
                    title={r.db_preview?.["Product"] || r.db_preview?.["Produkt"] || "-"} 
                    vendor={r.db_preview?.["Supplier"] || r.db_preview?.["Leverantör"] || "-"} 
                    sku={r.db_preview?.["Art.no"] || r.db_preview?.["Artikelnummer"] || "-"} 
                    market={r.db_preview?.["Market"] || r.db_preview?.["Marknad"] || ""}
                    language={r.db_preview?.["Language"] || r.db_preview?.["Språk"] || ""}
                  />
                )}
              </td>
              <td className="px-3 py-4 align-top">
                {r.decision === "auto_approved" && <Badge tone="green">Auto approved</Badge>}
                {r.decision === "approved" && <Badge tone="green">Approved</Badge>}
                {r.decision === "ai_auto_approved" && <Badge tone="green">AI auto approved</Badge>}
                {r.decision === "rejected" && <Badge tone="red">Rejected</Badge>}
                {r.decision === "auto_rejected" && <Badge tone="red">Auto-rejected</Badge>}
                {r.decision === "sent_to_ai" && <Badge tone="blue">Sent to AI</Badge>}
                {r.decision === "pending" && <Badge tone="yellow">Pending</Badge>}
              </td>
              <td className="px-3 py-4 align-top">
                <div className="text-sm font-semibold">{r.overall_score}</div>
              </td>
              <td className="px-3 py-4 align-top">
                <div className="text-sm">
                  {r.ai_confidence !== null && r.ai_confidence !== undefined ? (
                    <span className="text-blue-600 font-semibold">
                      {(r.ai_confidence * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </div>
              </td>
              <td className="px-3 py-4 align-top">
                <div className="max-w-[32rem] text-sm text-gray-700">{r.reason}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CardView({ results, selectedIds, onSelectionChange }: { results: MatchResultItem[]; selectedIds: number[]; onSelectionChange: (ids: number[]) => void }) {
  // Sort results according to priority:
  // 1. Lowest score first (highest priority)
  // 2. Rejected second
  // 3. Auto approved third
  // 4. Approved last (lowest priority)
  const sortedResults = [...results].sort((a, b) => {
    // First sort by decision priority
    const decisionPriority = (decision: string) => {
      switch (decision) {
        case "approved": return 5; // Lowest priority
        case "ai_auto_approved": return 4; // Fourth priority
        case "rejected": return 2; // Second priority
        case "auto_rejected": return 2; // Second priority (same as rejected)
        case "auto_approved": return 3; // Third priority
        default: return 1; // Highest priority (pending, sent_to_ai)
      }
    };
    
    const aPriority = decisionPriority(a.decision);
    const bPriority = decisionPriority(b.decision);
    
    if (aPriority !== bPriority) {
      return aPriority - bPriority;
    }
    
    // If same decision priority, sort by score (lowest first)
    return a.overall_score - b.overall_score;
  });

  return (
    <div className="grid grid-cols-1 gap-3">
      {sortedResults.map((r) => (
        <div key={r.id} className="group relative rounded-2xl border bg-white p-4 shadow-sm focus-within:ring-2 focus-within:ring-black">
          <div className="flex items-start gap-4">
            <input 
              type="checkbox" 
              className="mt-1 h-4 w-4 rounded border-gray-300" 
              checked={selectedIds.includes(r.id)}
              onChange={(e) => {
                if (e.target.checked) {
                  onSelectionChange([...selectedIds, r.id]);
                } else {
                  onSelectionChange(selectedIds.filter(id => id !== r.id));
                }
              }}
            />
            <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Imported data</div>
                <TripleCell 
                  title={r.customer_preview["Product"] || r.customer_preview["Produkt"] || "-"} 
                  vendor={r.customer_preview["Supplier"] || r.customer_preview["Leverantör"] || "-"} 
                  sku={r.customer_preview["Art.no"] || r.customer_preview["Artikelnummer"] || "-"} 
                  market={r.customer_preview["Market"] || r.customer_preview["Marknad"] || ""}
                  legislation={r.customer_preview["Legislation"] || r.customer_preview["Legislation"] || ""}
                  language={r.customer_preview["Language"] || r.customer_preview["Språk"] || ""}
                />
              </div>
              <div>
                <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Database data</div>
                {r.overall_score < 15 ? (
                  <div className="text-sm text-gray-500 italic">
                    Not on market & language
                  </div>
                ) : (
                  <TripleCell 
                    title={r.db_preview?.["Product"] || r.db_preview?.["Produkt"] || "-"} 
                    vendor={r.db_preview?.["Supplier"] || r.db_preview?.["Leverantör"] || "-"} 
                    sku={r.db_preview?.["Art.no"] || r.db_preview?.["Artikelnummer"] || "-"} 
                    market={r.db_preview?.["Market"] || r.db_preview?.["Marknad"] || ""}
                    legislation={r.db_preview?.["Legislation"] || r.db_preview?.["Legislation"] || ""}
                    language={r.db_preview?.["Language"] || r.db_preview?.["Språk"] || ""}
                  />
                )}
              </div>
            </div>
            <div className="ml-auto flex w-64 shrink-0 flex-col items-end gap-2">
              <div className="flex items-center gap-2">
                {/* Hover/Focus action buttons - positioned to left of status */}
                <div className="hidden items-center gap-2 group-hover:flex group-focus-within:flex">
                  <button 
                    onClick={() => onApprove(r.id)} 
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium bg-slate-100 hover:bg-slate-200"
                  >
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    Approve
                  </button>
                  <button 
                    onClick={() => onReject(r.id)} 
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium border hover:bg-slate-50"
                  >
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                    Reject
                  </button>
                  <button 
                    onClick={() => onSendToAI(r.id)} 
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium bg-[#0E1627] text-white hover:bg-[#121C32]"
                  >
                    <Send className="w-3 h-3" strokeWidth={2} />
                    Send to AI
                  </button>
                </div>
                
                <div>
                  {r.decision === "auto_approved" && <Badge tone="green">Auto approved</Badge>}
                  {r.decision === "approved" && <Badge tone="green">Approved</Badge>}
                  {r.decision === "ai_auto_approved" && <Badge tone="green">AI auto approved</Badge>}
                  {r.decision === "rejected" && <Badge tone="red">Rejected</Badge>}
                  {r.decision === "auto_rejected" && <Badge tone="red">Auto-rejected</Badge>}
                  {r.decision === "sent_to_ai" && <Badge tone="blue">Sent to AI</Badge>}
                  {r.decision === "pending" && <Badge tone="yellow">Pending</Badge>}
                </div>
              </div>
              <div className="text-sm">
                Score <span className="font-semibold">{r.overall_score}</span>
              </div>
              <div className="text-sm">
                AI-score: {r.ai_confidence !== null && r.ai_confidence !== undefined ? (
                  <span className="text-blue-600 font-semibold">
                    {(r.ai_confidence * 100).toFixed(0)}%
                  </span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </div>
              <div className="text-sm text-gray-700">{r.reason}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function MatchResults({ results, selectedIds, onSelectionChange, onApprove, onReject, onSendToAI, view, statusFilter, totalResults, filteredResults, startIndex, endIndex }: MatchResultsProps) {
  const [localView, setLocalView] = useState<'table' | 'card'>(view);
  
  // Filter results based on status with mapping
  const localFilteredResults = useMemo(() => {
    if (statusFilter === "all") {
      return results;
    }
    
    return results.filter(result => {
      switch (statusFilter) {
        case "review_required":
          // Pending & Sent to AI = Review required
          return result.decision === "pending" || result.decision === "sent_to_ai";
        case "approved":
          // Auto approved, Approved, AI auto approved = Approved
          return result.decision === "auto_approved" || 
                 result.decision === "approved" || 
                 result.decision === "ai_auto_approved";
        case "rejected":
          // Auto-rejected & Rejected = Rejected
          return result.decision === "auto_rejected" || result.decision === "rejected";
        default:
          return false;
      }
    });
  }, [results, statusFilter]);

  if (results.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No matches yet. Run matching to see results.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">
          <span>Showing <span className="font-bold">{startIndex !== undefined ? startIndex + 1 : 1}-{endIndex !== undefined ? Math.min(endIndex, filteredResults || 0) : (filteredResults || 0)}</span> of {totalResults || results.length} results</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm ${localView === 'table' ? 'font-semibold' : ''}`}>Table</span>
          <button
            onClick={() => setLocalView(localView === 'table' ? 'card' : 'table')}
            className="relative inline-flex h-8 w-14 items-center rounded-full border bg-white px-1 transition"
            aria-label="Toggle view"
          >
            <span className={`inline-block h-6 w-6 rounded-full bg-gray-800 transition-transform ${localView === 'card' ? 'translate-x-6' : 'translate-x-0'}`}></span>
          </button>
          <span className={`text-sm ${localView === 'card' ? 'font-semibold' : ''}`}>Card</span>
        </div>
      </div>

      {localView === "table" ? <TableView results={localFilteredResults} selectedIds={selectedIds} onSelectionChange={onSelectionChange} /> : <CardView results={localFilteredResults} selectedIds={selectedIds} onSelectionChange={onSelectionChange} />}

    </div>
  );
}

