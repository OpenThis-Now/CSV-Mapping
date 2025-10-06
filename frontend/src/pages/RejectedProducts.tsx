import React, { useEffect, useState, useMemo, useRef } from "react";
import api, { SupplierData, SupplierMappingSummary, SupplierMatchResult } from "@/lib/api";
import { useToast } from "@/contexts/ToastContext";
import {
  Upload,
  Search,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Paperclip,
  Filter,
  PlayCircle,
  RefreshCw,
  Link2
} from "lucide-react";

interface RejectedProduct {
  id: number;
  match_result_id: number;
  product_name: string;
  supplier: string;
  article_number?: string;
  company_id?: string;
  pdf_filename?: string;
  pdf_source?: string;
  status: "needs_data" | "complete" | "sent" | "request_worklist";
  created_at: string;
  completed_at?: string;
  notes?: string;
  customer_data: Record<string, any>;
  reason: string;
}

interface RejectedProductsProps {
  projectId: number;
}

/******** Helpers ********/
const toneFor = (status = "") => {
  if (status.includes("missing")) return "amber";
  if (status === "ready_for_db_import") return "green";
  return "gray";
};

const filterByQuery = (items: RejectedProduct[] = [], q = "") => {
  const s = q.toLowerCase();
  return items.filter((p) => p.product_name.toLowerCase().includes(s));
};

function getStatusText(status: string) {
    const texts = {
      ready_for_db_import: "Ready for DB import",
    pdf_companyid_missing: "PDF & CompanyID Missing",
    pdf_missing: "PDF Missing",
    companyid_missing: "CompanyID Missing",
      request_worklist: "Ready for DB import" // Legacy support
    };
    return texts[status as keyof typeof texts] || status;
}

/******** UI atoms ********/
function Pill({ tone = "gray", children }) {
  const map = {
    gray: "bg-gray-100 text-gray-700",
    amber: "bg-amber-100 text-amber-800",
    green: "bg-emerald-100 text-emerald-800",
    blue: "bg-blue-100 text-blue-800",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${map[tone] || map.gray}`}>
      {children}
    </span>
  );
}

function Dropzone({ onFile, accept = ".pdf", label = "Drag & drop file here or click to select" }) {
  const [isOver, setIsOver] = useState(false);
    return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed px-4 py-3 text-sm ${
        isOver ? "border-blue-400 bg-blue-50" : "border-gray-200 hover:bg-gray-50"
      }`}
    >
      <Upload className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </label>
  );
}

/******** Top Actions (shared) ********/
function TopActions({ onExportCsv, onExportZip }) {
    return (
    <div className="sticky top-0 z-10 -mx-4 mb-6 border-b bg-white/80 p-4 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onExportCsv} className="rounded-full bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200 hover:bg-emerald-100">
          Export Completed (CSV)
        </button>
        <button onClick={onExportZip} className="rounded-full bg-violet-50 px-3 py-2 text-sm font-medium text-violet-700 ring-1 ring-inset ring-violet-200 hover:bg-violet-100">
          Export Ready for DB import (CSV + ZIP)
        </button>
        <div className="ms-auto flex items-center gap-2 text-xs text-gray-500">
          <Filter className="h-4 w-4" />
          <span>Show:</span>
          <select className="rounded-full border-gray-200 text-xs focus:border-blue-500 focus:ring-blue-500">
            <option>All</option>
            <option>PDF Missing</option>
            <option>CompanyID Missing</option>
            <option>Marked as Done</option>
          </select>
        </div>
        </div>
      </div>
    );
  }

/******** Product Row ********/
function ProductRow({ 
  product, 
  index, 
  onSave, 
  onUpload, 
  onUpdateProduct,
  uploadingPdf 
}: {
  product: RejectedProduct;
  index: number;
  onSave: (data: any) => void;
  onUpload: (productId: number, file: File) => void;
  onUpdateProduct: (productId: number, data: any) => void;
  uploadingPdf: number | null;
}) {
  const [open, setOpen] = useState(false); // Changed: start closed instead of index === 0
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [companyId, setCompanyId] = useState(product.company_id || "");
  const [notes, setNotes] = useState(product.notes || "");
  const [status, setStatus] = useState(product.status);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Update local state when product data changes (e.g., after PDF upload)
  useEffect(() => {
    setCompanyId(product.company_id || "");
    setNotes(product.notes || "");
    setStatus(product.status);
    // Clear the selected file if a PDF is now linked
    if (product.pdf_filename) {
      setFile(null);
    }
  }, [product.company_id, product.notes, product.status, product.pdf_filename]);

  // Auto-update status based on PDF and CompanyID availability
  useEffect(() => {
    const hasPdf = product.pdf_filename || file;
    const hasCompanyId = companyId.trim() !== "";
    
    if (hasPdf && hasCompanyId) {
      setStatus("ready_for_db_import");
    } else if (hasPdf && !hasCompanyId) {
      setStatus("companyid_missing");
    } else if (!hasPdf && hasCompanyId) {
      setStatus("pdf_missing");
    } else {
      setStatus("pdf_companyid_missing");
    }
  }, [product.pdf_filename, file, companyId]);

  const tone = toneFor(status);
  const statusText = getStatusText(status);

  const handleUpload = (f: File) => {
    setFile(f);
    setUploading(true);
    onUpload(product.id, f);
    // Don't set uploading to false here - let the parent component handle it
  };

  const handleSave = () => {
    onSave({
      company_id: companyId,
      notes: notes,
      status: status
    });
  };

  return (
    <div className="rounded-2xl border bg-white shadow-sm">
      <div onClick={() => setOpen(!open)} role="button" className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="truncate text-base font-semibold">{product.product_name}</div>
            <Pill tone={tone}>{statusText}</Pill>
            {file && <Pill tone="green">PDF Selected</Pill>}
            {product.pdf_filename && <Pill tone="green"><Paperclip className="h-3.5 w-3.5"/> Linked</Pill>}
          </div>
          <div className="mt-1 line-clamp-1 text-xs text-gray-500">
            {product.supplier} • {product.article_number || 'No article number'} • {product.reason}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="sr-only"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
          <button
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            className="rounded-full p-2 md:opacity-0 md:group-hover:opacity-100 hover:bg-gray-100 focus:opacity-100 focus:outline-none"
            title="Upload PDF"
            aria-label="Upload PDF"
          >
            {uploading || uploadingPdf === product.id ? (
              <Loader2 className="h-4 w-4 animate-spin text-gray-600" />
            ) : (
              <Upload className="h-4 w-4 text-gray-600" />
            )}
          </button>
          {open ? <ChevronUp className="h-5 w-5 text-gray-400"/> : <ChevronDown className="h-5 w-5 text-gray-400"/>}
        </div>
      </div>

      {open && (
        <div className="grid gap-5 border-t px-5 py-5 md:grid-cols-3">
          <div className="md:col-span-1">
            <div className="text-xs font-medium text-gray-700">Upload PDF</div>
            <div className="mt-2">
              <Dropzone onFile={handleUpload} />
              {/* Only show newly selected file if it's different from the linked PDF */}
              {file && file.name !== product.pdf_filename && (
                <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs">
                  <Paperclip className="h-3.5 w-3.5"/> {file.name}
                </div>
              )}
              {/* Show linked PDF */}
              {product.pdf_filename && (
                <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-green-100 px-3 py-1 text-xs">
                  <Paperclip className="h-3.5 w-3.5"/> {product.pdf_filename}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3 md:col-span-1">
                      <div>
              <label className="text-xs font-medium text-gray-700">Company ID</label>
              <div className="mt-1 flex gap-2">
                <input value={companyId} onChange={(e) => setCompanyId(e.target.value)} placeholder="Enter Company ID" className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"/>
                          <button
                            onClick={async () => {
                    // Auto-match functionality
                    try {
                      await api.post(`/projects/${product.match_result_id}/rejected-products/${product.id}/auto-match`);
                      // Reload or update state
                              } catch (error) {
                                console.error("Auto-match failed:", error);
                              }
                            }}
                  className="inline-flex items-center gap-1 rounded-xl border border-gray-200 px-3 text-xs hover:bg-gray-50"
                          >
                  <Search className="h-4 w-4"/> Auto-match
                          </button>
                        </div>
                      </div>
                      <div>
              <label className="text-xs font-medium text-gray-700">Status</label>
              <select 
                value={status}
                onChange={(e) => setStatus(e.target.value as any)}
                className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              >
                <option value="ready_for_db_import">Ready for DB import</option>
                <option value="pdf_companyid_missing">PDF & CompanyID Missing</option>
                <option value="pdf_missing">PDF Missing</option>
                <option value="companyid_missing">CompanyID Missing</option>
              </select>
                      </div>
                    </div>

          <div className="space-y-3 md:col-span-1">
            <div>
              <label className="text-xs font-medium text-gray-700">Notes</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="Add any notes here" className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"/>
                    </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleSave} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
                <CheckCircle2 className="h-4 w-4"/> Save
              </button>
              <button onClick={() => {
                handleSave();
                // onNext functionality could be added here
              }} className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50">
                Save & Next
              </button>
            </div>
                  </div>
          </div>
      )}
    </div>
  );
}

/******** Products Tab ********/
function ProductsTab({ 
  products, 
  query, 
  setQuery, 
  onUpdateProduct, 
  onUploadPdf, 
  uploadingPdf, 
  onExportCompleted, 
  onExportWorklist, 
  onUploadZip, 
  uploadingZip 
}: {
  products: RejectedProduct[];
  query: string;
  setQuery: (q: string) => void;
  onUpdateProduct: (productId: number, data: any) => void;
  onUploadPdf: (productId: number, file: File) => void;
  uploadingPdf: number | null;
  onExportCompleted: () => void;
  onExportWorklist: () => void;
  onUploadZip: (file: File) => void;
  uploadingZip: boolean;
}) {
  const filtered = useMemo(() => filterByQuery(products, query), [products, query]);

  const onSave = (payload: any) => {
    onUpdateProduct(payload.id, payload);
  };

  return (
    <>
      <TopActions onExportCsv={onExportCompleted} onExportZip={onExportWorklist}/>

      {/* Bulk ZIP upload */}
      <div className="bg-white rounded-xl border p-4 mb-6">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <h3 className="font-semibold mb-2">Bulk PDF Upload</h3>
            <p className="text-sm text-gray-600 mb-3">Upload a ZIP with PDFs. The system will try to auto-assign based on filename.</p>
            <input type="file" accept=".zip" className="text-sm" onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUploadZip(f);
            }}/>
          </div>
          {uploadingZip && <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"/>}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 rounded-xl border bg-white px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-gray-400"/>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products…" className="w-64 text-sm outline-none"/>
                </div>
        <div className="text-sm text-gray-500">{filtered.length} products</div>
              </div>

      <div className="grid gap-4">
        {filtered.map((p, idx) => (
          <ProductRow 
            key={p.id} 
            product={p} 
            index={idx} 
            onSave={onSave} 
            onUpload={onUploadPdf}
            onUpdateProduct={onUpdateProduct}
            uploadingPdf={uploadingPdf}
          />
        ))}
      </div>
    </>
  );
}

/******** Supplier Mapping Tab ********/
function SupplierMappingTab({ 
  suppliers,
  supplierMapping,
  supplierMatchResult,
  onUploadSuppliersCSV,
  onRunSupplierMatching,
  onApplySupplierMatches,
  uploadingSuppliers,
  matchingSuppliers,
  applyingMatches
}: {
  suppliers: SupplierData[];
  supplierMapping: SupplierMappingSummary | null;
  supplierMatchResult: SupplierMatchResult | null;
  onUploadSuppliersCSV: (file: File) => void;
  onRunSupplierMatching: () => void;
  onApplySupplierMatches: () => void;
  uploadingSuppliers: boolean;
  matchingSuppliers: boolean;
  applyingMatches: boolean;
}) {
  const [csv, setCsv] = useState<File | null>(null);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Upload Suppliers CSV</h3>
            <p className="mt-1 text-sm text-gray-500">Upload a CSV with supplier data. Required: Supplier name, CompanyID, Country. Optional: Total.</p>
                </div>
          <button onClick={onRunSupplierMatching} disabled={!csv || matchingSuppliers} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-blue-300">
            {matchingSuppliers ? <Loader2 className="h-4 w-4 animate-spin"/> : <PlayCircle className="h-4 w-4"/>} Run AI Matching
          </button>
              </div>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2">
            <Dropzone accept=".csv" onFile={(file) => {
              setCsv(file);
              onUploadSuppliersCSV(file);
            }} label="Drag & drop CSV here or click to select"/>
            {csv && <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs"><Paperclip className="h-3.5 w-3.5"/>{csv.name}</div>}
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-medium text-gray-700">CSV Format</summary>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-gray-600">
                <li><b>Supplier name</b> – supplier/company name</li>
                <li><b>CompanyID</b> – company identifier</li>
                <li><b>Country</b> – country/market code</li>
                <li><b>Total</b> – product count (optional)</li>
              </ul>
            </details>
                            </div>
          <div className="space-y-3">
            <div className="rounded-2xl border bg-white p-5 shadow-sm">
              <div className="text-2xl font-semibold">{supplierMapping?.supplier_summary.length || 0}</div>
              <div className="text-sm text-gray-500">Unique suppliers</div>
            </div>
            <div className="rounded-2xl border bg-white p-5 shadow-sm">
              <div className="text-2xl font-semibold">{supplierMapping?.total_unmatched_products || 0}</div>
              <div className="text-sm text-gray-500">Total products</div>
            </div>
            <div className="rounded-2xl border bg-white p-5 shadow-sm">
              <div className="text-2xl font-semibold">{suppliers.length}</div>
              <div className="text-sm text-gray-500">CSV suppliers</div>
            </div>
          </div>
                        </div>
                      </div>

      <div className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">Suppliers without matches</h3>
          <button onClick={onRunSupplierMatching} className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-3 py-1.5 text-xs hover:bg-gray-50">
            <RefreshCw className="h-3.5 w-3.5"/> Try again
          </button>
        </div>
        <ul className="mt-3 divide-y">
          {supplierMapping?.supplier_summary.map((supplier, index) => (
            <li key={index} className="flex items-center justify-between py-3 text-sm">
              <div>
                <div className="font-medium">{supplier.supplier_name}</div>
                <div className="text-xs text-gray-500">Country: {supplier.country} • Products: {supplier.product_count}</div>
              </div>
              <button className="rounded-full bg-gray-100 px-3 py-1 text-xs">View</button>
            </li>
          ))}
        </ul>
      </div>

      {/* AI Matching Results */}
      {supplierMatchResult && (
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">AI Matching Results</h3>
            <button
              onClick={onApplySupplierMatches}
              disabled={applyingMatches}
              className="inline-flex items-center gap-2 rounded-xl bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-green-300"
            >
              {applyingMatches ? <Loader2 className="h-4 w-4 animate-spin"/> : <CheckCircle2 className="h-4 w-4"/>} Apply Matches
            </button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-green-50 p-4 rounded-lg border border-green-200">
              <div className="text-2xl font-bold text-green-800">{supplierMatchResult.summary.total_matched}</div>
              <div className="text-sm text-green-600">Exact Matches</div>
            </div>
            <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
              <div className="text-2xl font-bold text-yellow-800">{supplierMatchResult.summary.new_country_needed}</div>
              <div className="text-sm text-yellow-600">New Country Needed</div>
            </div>
            <div className="bg-red-50 p-4 rounded-lg border border-red-200">
              <div className="text-2xl font-bold text-red-800">{supplierMatchResult.summary.new_supplier_needed}</div>
              <div className="text-sm text-red-600">New Supplier Needed</div>
            </div>
          </div>

          {/* Exact Matches */}
          {supplierMatchResult.matched_suppliers.length > 0 && (
            <div className="mb-6">
              <h4 className="font-medium mb-3 text-green-800">Exact Matches</h4>
              <div className="space-y-2">
                {supplierMatchResult.matched_suppliers.map((match, index) => (
                  <div key={index} className="border border-green-200 rounded-lg p-3 bg-green-50">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium">{match.supplier_name} ({match.country})</div>
                        <div className="text-sm text-gray-600">
                          → {match.matched_supplier.supplier_name} ({match.matched_supplier.country}) 
                          • CompanyID: {match.matched_supplier.company_id}
                        </div>
                        <div className="text-sm text-green-600">Products affected: {match.products_affected}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* New Country Needed */}
          {supplierMatchResult.new_country_needed.length > 0 && (
            <div className="mb-6">
              <h4 className="font-medium mb-3 text-yellow-800">New Country Needed</h4>
              <div className="space-y-2">
                {supplierMatchResult.new_country_needed.map((match, index) => (
                  <div key={index} className="border border-yellow-200 rounded-lg p-3 bg-yellow-50">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium">{match.supplier_name} (current: {match.current_country})</div>
                        <div className="text-sm text-gray-600">
                          → {match.matched_supplier.supplier_name} (available in: {match.matched_supplier.country})
                          • CompanyID: {match.matched_supplier.company_id}
                        </div>
                        <div className="text-sm text-yellow-600">Products affected: {match.products_affected}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* New Supplier Needed */}
          {supplierMatchResult.new_supplier_needed.length > 0 && (
            <div className="mb-6">
              <h4 className="font-medium mb-3 text-red-800">New Supplier Needed</h4>
              <div className="space-y-2">
                {supplierMatchResult.new_supplier_needed.map((match, index) => (
                  <div key={index} className="border border-red-200 rounded-lg p-3 bg-red-50">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium">{match.supplier_name} ({match.country})</div>
                        <div className="text-sm text-red-600">No matching supplier found in CSV</div>
                        <div className="text-sm text-red-600">Products affected: {match.products_affected}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/******** Main ********/
export default function RejectedProducts({ projectId }: RejectedProductsProps) {
  const [products, setProducts] = useState<RejectedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [uploadingPdf, setUploadingPdf] = useState<number | null>(null);
  const [uploadingZip, setUploadingZip] = useState(false);
  const [tab, setTab] = useState("products");
  
  // Supplier-related state
  const [suppliers, setSuppliers] = useState<SupplierData[]>([]);
  const [supplierMapping, setSupplierMapping] = useState<SupplierMappingSummary | null>(null);
  const [supplierMatchResult, setSupplierMatchResult] = useState<SupplierMatchResult | null>(null);
  const [uploadingSuppliers, setUploadingSuppliers] = useState(false);
  const [matchingSuppliers, setMatchingSuppliers] = useState(false);
  const [applyingMatches, setApplyingMatches] = useState(false);
  
  const { showToast } = useToast();

  const loadProducts = async () => {
    try {
      const res = await api.get(`/projects/${projectId}/rejected-products`);
      setProducts(res.data);
      
      // Automatically link PDFs from customer import after loading products
      try {
        const linkRes = await api.post(`/projects/${projectId}/rejected-products/link-pdfs`);
        if (linkRes.data.linked_count > 0) {
          showToast(`Automatically linked ${linkRes.data.linked_count} PDFs from customer import`, 'success');
          // Reload products to show updated PDF links and status
          const updatedRes = await api.get(`/projects/${projectId}/rejected-products`);
          setProducts(updatedRes.data);
        }
      } catch (linkError) {
        // Silently handle link errors - not critical for main functionality
        console.log("Auto-linking PDFs failed (non-critical):", linkError);
      }
    } catch (error) {
      console.error("Failed to load rejected products:", error);
      showToast("Failed to load rejected products", 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadSuppliers = async () => {
    try {
      const res = await api.get(`/projects/${projectId}/suppliers`);
      setSuppliers(res.data);
    } catch (error) {
      console.error("Failed to load suppliers:", error);
      showToast("Failed to load suppliers", 'error');
    }
  };

  const loadSupplierMapping = async () => {
    try {
      const res = await api.get(`/projects/${projectId}/supplier-mapping`);
      setSupplierMapping(res.data);
    } catch (error) {
      console.error("Failed to load supplier mapping:", error);
      showToast("Failed to load supplier mapping", 'error');
    }
  };

  useEffect(() => {
    loadProducts();
    loadSuppliers();
    loadSupplierMapping();
  }, [projectId]);

  const updateProduct = async (productId: number, data: Partial<RejectedProduct>) => {
    try {
      await api.put(`/projects/${projectId}/rejected-products/${productId}`, data);
      showToast("Product updated successfully", 'success');
      await loadProducts();
    } catch (error) {
      console.error("Failed to update product:", error);
      showToast("Failed to update product", 'error');
    }
  };

  const uploadPdf = async (productId: number, file: File) => {
    setUploadingPdf(productId);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await api.post(`/projects/${projectId}/rejected-products/${productId}/upload-pdf`, formData);
      showToast("PDF uploaded successfully", 'success');
      
      // Reload products to get updated status and PDF filename
      await loadProducts();
    } catch (error) {
      console.error("Failed to upload PDF:", error);
      showToast("Failed to upload PDF", 'error');
    } finally {
      setUploadingPdf(null);
    }
  };

  const uploadZip = async (file: File) => {
    setUploadingZip(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await api.post(`/projects/${projectId}/rejected-products/upload-zip`, formData);
      showToast(`ZIP uploaded: ${res.data.assigned_count} PDFs auto-assigned`, 'success');
      await loadProducts();
    } catch (error) {
      console.error("Failed to upload ZIP:", error);
      showToast("Failed to upload ZIP", 'error');
    } finally {
      setUploadingZip(false);
    }
  };

  const downloadFile = async (url: string, filename: string) => {
    try {
      // Get the base URL from the API instance
      const baseURL = api.defaults.baseURL;
      const fullUrl = url.startsWith('/api/') ? `${baseURL}${url.replace('/api', '')}` : url;
      
      console.log('Downloading from:', fullUrl);
      
      // Use fetch to get the file as blob, then create download link
      const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/octet-stream, application/zip, application/csv, */*',
        },
      });
      
      if (!response.ok) {
        throw new Error(`Download failed: ${response.status} ${response.statusText}`);
      }
      
      const blob = await response.blob();
      console.log('Downloaded blob size:', blob.size, 'type:', blob.type);
      
      // Create download link
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up the object URL
      setTimeout(() => {
        window.URL.revokeObjectURL(downloadUrl);
      }, 1000);
      
    } catch (error) {
      console.error('Download failed:', error);
      showToast('Failed to download file', 'error');
    }
  };

  const exportCompleted = async () => {
    try {
      const res = await api.get(`/projects/${projectId}/rejected-products/export-csv`);
      if (res.data.count === 0) {
        showToast(res.data.message, 'info');
      } else {
        showToast(`CSV export completed: ${res.data.count} products exported`, 'success');
        // Download the CSV file
        const downloadUrl = `/projects/${projectId}/rejected-products/download/${res.data.filename}`;
        await downloadFile(downloadUrl, res.data.filename);
      }
    } catch (error) {
      console.error("Failed to export:", error);
      showToast("Failed to export completed products", 'error');
    }
  };

  const exportWorklist = async () => {
    try {
      const res = await api.get(`/projects/${projectId}/rejected-products/export-worklist`);
      if (res.data.count === 0) {
        showToast(res.data.message, 'info');
      } else {
        showToast(`Worklist export completed: ${res.data.count} products exported (CSV + ZIP)`, 'success');
        // Download the ZIP file (contains both CSV and PDFs)
        const downloadUrl = `/projects/${projectId}/rejected-products/download/${res.data.zip_filename}`;
        await downloadFile(downloadUrl, res.data.zip_filename);
      }
    } catch (error) {
      console.error("Failed to export worklist:", error);
      showToast("Failed to export worklist products", 'error');
    }
  };

  const uploadSuppliersCSV = async (file: File) => {
    setUploadingSuppliers(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await api.post(`/projects/${projectId}/suppliers/upload`, formData);
      
      // Show more detailed message
      if (res.data.suppliers_count === 0) {
        showToast("CSV uploaded but no suppliers were added. Please check that your CSV has the correct column names: 'Supplier name', 'CompanyID', 'Country', 'Total'", 'warning');
      } else {
        showToast(res.data.message, 'success');
      }
      
      await loadSuppliers();
      await loadSupplierMapping();
    } catch (error: any) {
      console.error("Failed to upload suppliers CSV:", error);
      const errorMessage = error.response?.data?.detail || "Failed to upload suppliers CSV";
      showToast(errorMessage, 'error');
    } finally {
      setUploadingSuppliers(false);
    }
  };

  const runSupplierMatching = async () => {
    setMatchingSuppliers(true);
    try {
      const res = await api.post(`/projects/${projectId}/suppliers/ai-match`);
      setSupplierMatchResult(res.data);
      showToast(`AI matching completed. Found ${res.data.summary.total_matched} matches, ${res.data.summary.new_country_needed} need new country, ${res.data.summary.new_supplier_needed} need new supplier.`, 'success');
    } catch (error) {
      console.error("Failed to run supplier matching:", error);
      showToast("Failed to run supplier matching", 'error');
    } finally {
      setMatchingSuppliers(false);
    }
  };

  const applySupplierMatches = async () => {
    setApplyingMatches(true);
    try {
      const res = await api.post(`/projects/${projectId}/suppliers/apply-matches`);
      showToast(res.data.message, 'success');
      await loadProducts();
      await loadSupplierMapping();
      setSupplierMatchResult(null);
    } catch (error) {
      console.error("Failed to apply supplier matches:", error);
      showToast("Failed to apply supplier matches", 'error');
    } finally {
      setApplyingMatches(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="text-gray-500 mb-4">No rejected products found</div>
        <div className="text-sm text-gray-400">
          Rejected products will appear here after running matching
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-20">
      <div className="mb-5 mt-2 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Rejected Products</h1>
        <div className="rounded-xl bg-gray-100 px-3 py-1 text-xs text-gray-600">Project: {projectId}</div>
      </div>

      <div className="mb-6 inline-flex rounded-xl border bg-white p-1 shadow-sm">
        <button onClick={() => setTab("products")} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "products" ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-50"}`}>Products</button>
        <button onClick={() => setTab("mapping")} className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "mapping" ? "bg-gray-900 text-white" : "text-gray-700 hover:bg-gray-50"}`}>Supplier Mapping</button>
      </div>

      {tab === "products" ? (
        <ProductsTab 
          products={products}
          query={query}
          setQuery={setQuery}
          onUpdateProduct={updateProduct}
          onUploadPdf={uploadPdf}
          uploadingPdf={uploadingPdf}
          onExportCompleted={exportCompleted}
          onExportWorklist={exportWorklist}
          onUploadZip={uploadZip}
          uploadingZip={uploadingZip}
        />
      ) : (
        <SupplierMappingTab 
          suppliers={suppliers}
          supplierMapping={supplierMapping}
          supplierMatchResult={supplierMatchResult}
          onUploadSuppliersCSV={uploadSuppliersCSV}
          onRunSupplierMatching={runSupplierMatching}
          onApplySupplierMatches={applySupplierMatches}
          uploadingSuppliers={uploadingSuppliers}
          matchingSuppliers={matchingSuppliers}
          applyingMatches={applyingMatches}
        />
      )}
    </div>
  );
}