import React, { useMemo, useState } from "react";
import { MatchResultItem } from "@/lib/api";
import CountryFlag from "./CountryFlag";

interface MatchResultsProps {
  results: MatchResultItem[];
  selectedIds: number[];
  onSelectionChange: (ids: number[]) => void;
  view: "table" | "card";
  statusFilter: string;
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
  // 2. Auto approved second
  // 3. Not approved third
  // 4. Approved last (lowest priority)
  const sortedResults = [...results].sort((a, b) => {
    // First sort by decision priority
    const decisionPriority = (decision: string) => {
      switch (decision) {
        case "approved": return 5; // Lowest priority
        case "ai_auto_approved": return 4; // Fourth priority
        case "not_approved": return 3; // Third priority
        case "auto_rejected": return 3; // Third priority (same as not_approved)
        case "auto_approved": return 2; // Second priority
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
                <TripleCell 
                  title={r.db_preview?.["Product"] || r.db_preview?.["Produkt"] || "-"} 
                  vendor={r.db_preview?.["Supplier"] || r.db_preview?.["Leverantör"] || "-"} 
                  sku={r.db_preview?.["Art.no"] || r.db_preview?.["Artikelnummer"] || "-"} 
                  market={r.db_preview?.["Market"] || r.db_preview?.["Marknad"] || ""}
                  language={r.db_preview?.["Language"] || r.db_preview?.["Språk"] || ""}
                />
              </td>
              <td className="px-3 py-4 align-top">
                {r.decision === "auto_approved" && <Badge tone="green">auto_approved</Badge>}
                {r.decision === "approved" && <Badge tone="green">approved</Badge>}
                {r.decision === "ai_auto_approved" && <Badge tone="green">AI-auto approved</Badge>}
                {r.decision === "not_approved" && <Badge tone="red">not_approved</Badge>}
                {r.decision === "auto_rejected" && <Badge tone="red">Auto-rejected</Badge>}
                {r.decision === "sent_to_ai" && <Badge tone="blue">sent_to_ai</Badge>}
                {r.decision === "pending" && <Badge tone="yellow">pending</Badge>}
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
  // 2. Auto approved second
  // 3. Not approved third
  // 4. Approved last (lowest priority)
  const sortedResults = [...results].sort((a, b) => {
    // First sort by decision priority
    const decisionPriority = (decision: string) => {
      switch (decision) {
        case "approved": return 5; // Lowest priority
        case "ai_auto_approved": return 4; // Fourth priority
        case "not_approved": return 3; // Third priority
        case "auto_rejected": return 3; // Third priority (same as not_approved)
        case "auto_approved": return 2; // Second priority
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
        <div key={r.id} className="rounded-2xl border bg-white p-4 shadow-sm">
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
                <TripleCell 
                  title={r.db_preview?.["Product"] || r.db_preview?.["Produkt"] || "-"} 
                  vendor={r.db_preview?.["Supplier"] || r.db_preview?.["Leverantör"] || "-"} 
                  sku={r.db_preview?.["Art.no"] || r.db_preview?.["Artikelnummer"] || "-"} 
                  market={r.db_preview?.["Market"] || r.db_preview?.["Marknad"] || ""}
                  legislation={r.db_preview?.["Legislation"] || r.db_preview?.["Legislation"] || ""}
                  language={r.db_preview?.["Language"] || r.db_preview?.["Språk"] || ""}
                />
              </div>
            </div>
            <div className="ml-auto flex w-64 shrink-0 flex-col items-end gap-2">
              <div>
                {r.decision === "auto_approved" && <Badge tone="green">auto_approved</Badge>}
                {r.decision === "approved" && <Badge tone="green">approved</Badge>}
                {r.decision === "ai_auto_approved" && <Badge tone="green">AI-auto approved</Badge>}
                {r.decision === "not_approved" && <Badge tone="red">not_approved</Badge>}
                {r.decision === "auto_rejected" && <Badge tone="red">Auto-rejected</Badge>}
                {r.decision === "sent_to_ai" && <Badge tone="blue">sent_to_ai</Badge>}
                {r.decision === "pending" && <Badge tone="yellow">pending</Badge>}
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

export default function MatchResults({ results, selectedIds, onSelectionChange, view, statusFilter }: MatchResultsProps) {
  const [localView, setLocalView] = useState<'table' | 'card'>(view);
  
  // Filter results based on status
  const filteredResults = useMemo(() => {
    if (statusFilter === "all") {
      return results;
    }
    return results.filter(result => result.decision === statusFilter);
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
          {statusFilter !== "all" && (
            <span>Showing {filteredResults.length} of {results.length} results</span>
          )}
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

      {localView === "table" ? <TableView results={filteredResults} selectedIds={selectedIds} onSelectionChange={onSelectionChange} /> : <CardView results={filteredResults} selectedIds={selectedIds} onSelectionChange={onSelectionChange} />}

      <p className="text-xs text-gray-500">
        Tip: The scale of the product name is controlled by <code className="rounded bg-gray-100 px-1">text-base font-semibold</code> – 
        increase to <code className="rounded bg-gray-100 px-1">text-lg</code> if you want to make it even clearer.
      </p>
    </div>
  );
}

