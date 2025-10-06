import React, { useEffect, useState, useMemo, useRef } from "react";
import api, { SupplierData, SupplierMappingSummary, SupplierMatchResult } from "@/lib/api";
import { useToast } from "@/contexts/ToastContext";

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

/***********************************
 * Helper functions
 ***********************************/
function computeStatusTone(status = "") {
  if (!status) return "gray";
  if (status.includes("missing")) return "amber";
  if (status === "ready_for_db_import") return "green";
  return "gray";
}

function filterProductsByQuery(products: RejectedProduct[] = [], q = "") {
  const query = String(q).toLowerCase();
  return products.filter((p) => p.product_name.toLowerCase().includes(query));
}

function getStatusText(status: string) {
  const texts = {
    ready_for_db_import: "Ready for DB import",
    pdf_companyid_missing: "PDF & CompanyID missing",
    pdf_missing: "PDF missing",
    companyid_missing: "CompanyID missing",
    request_worklist: "Ready for DB import" // Legacy support
  };
  return texts[status as keyof typeof texts] || status;
}

/***********************************
 * UI Components
 ***********************************/
function Pill({ tone = "gray", children }: { tone?: string; children: React.ReactNode }) {
  const map = {
    gray: "bg-gray-100 text-gray-700",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-rose-100 text-rose-700",
    green: "bg-emerald-100 text-emerald-800",
    indigo: "bg-indigo-100 text-indigo-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${map[tone as keyof typeof map] || map.gray}`}>
      {children}
    </span>
  );
}

function TopActions({ onExportCompleted, onExportWorklist }: {
  onExportCompleted: () => void;
  onExportWorklist: () => void;
}) {
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-6 border-b bg-white/80 p-4 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="flex flex-wrap items-center gap-2">
        <button 
          onClick={onExportCompleted}
          className="rounded-full bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200 hover:bg-emerald-100"
        >
          Export Completed (CSV)
        </button>
        <button 
          onClick={onExportWorklist}
          className="rounded-full bg-violet-50 px-3 py-2 text-sm font-medium text-violet-700 ring-1 ring-inset ring-violet-200 hover:bg-violet-100"
        >
          Export Ready for DB import (CSV + ZIP)
        </button>
        <div className="ms-auto flex items-center gap-2 text-xs text-gray-500">
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

/***********************************
 * Product Row Component
 ***********************************/
function ProductRow({ 
  product, 
  index, 
  onSave, 
  onNext, 
  onUploadPdf, 
  onUpdateProduct,
  uploadingPdf 
}: {
  product: RejectedProduct;
  index: number;
  onSave: (data: any) => void;
  onNext: () => void;
  onUploadPdf: (productId: number, file: File) => void;
  onUpdateProduct: (productId: number, data: any) => void;
  uploadingPdf: number | null;
}) {
  const [open, setOpen] = useState(index === 0);
  const [file, setFile] = useState<File | null>(null);
  const [companyId, setCompanyId] = useState(product.company_id || "");
  const [notes, setNotes] = useState(product.notes || "");
  const [status, setStatus] = useState(product.status);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const statusTone = computeStatusTone(status);
  const statusText = getStatusText(status);

  const handleSave = () => {
    onSave({
      company_id: companyId,
      notes: notes,
      status: status
    });
  };

  const handleFileUpload = (uploadedFile: File) => {
    setFile(uploadedFile);
    onUploadPdf(product.id, uploadedFile);
  };

  return (
    <div className="rounded-2xl border bg-white shadow-sm">
      {/* Header (click to expand) */}
      <div onClick={() => setOpen(!open)} role="button" className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 mb-2">
            <div className="truncate text-base font-semibold">{product.product_name}</div>
            <Pill tone={statusTone}>{statusText}</Pill>
            {file && <Pill tone="green">PDF Selected</Pill>}
            {product.pdf_filename && <Pill tone="green">PDF Linked</Pill>}
          </div>
          {/* Always visible supplier and article info */}
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <div className="flex items-center gap-1">
              <span className="font-medium">Supplier:</span>
              <span>{product.supplier}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="font-medium">Article:</span>
              <span>{product.article_number || 'N/A'}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="font-medium">Reason:</span>
              <span className="text-gray-500">{product.reason}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {/* Invisible file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              handleFileUpload(f);
            }}
          />
          {/* Upload button (doesn't toggle row) */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
            className="rounded-full p-2 md:opacity-0 md:group-hover:opacity-100 hover:bg-gray-100 focus:opacity-100 focus:outline-none"
            title="Upload PDF"
            aria-label="Upload PDF"
          >
            {uploadingPdf === product.id ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600"></div>
            ) : (
              <div className="h-4 w-4 text-gray-600">📁</div>
            )}
          </button>
          {open ? <div className="h-5 w-5 text-gray-400">▲</div> : <div className="h-5 w-5 text-gray-400">▼</div>}
        </div>
      </div>

      {/* Expanded content */}
      {open && (
        <div className="grid gap-5 border-t px-5 py-5 md:grid-cols-3">
          {/* Column: Quick PDF upload */}
          <div className="md:col-span-1">
            <div className="text-xs font-medium text-gray-700">Upload PDF</div>
            <div className="mt-2">
              <label className="flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed border-gray-200 px-4 py-3 text-sm hover:bg-gray-50">
                <div className="h-4 w-4 text-gray-400">📁</div>
                <span className="truncate">Click to select PDF</span>
                <input type="file" accept=".pdf" className="sr-only" onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])} />
              </label>
              {file && (
                <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-gray-100 px-3 py-1 text-xs">
                  {file.name}
                </div>
              )}
              {product.pdf_filename && (
                <div className="mt-2 inline-flex items-center gap-2 rounded-full bg-green-100 px-3 py-1 text-xs">
                  {product.pdf_filename}
                </div>
              )}
            </div>
          </div>

          {/* Column: Meta */}
          <div className="space-y-3 md:col-span-1">
            <div>
              <label className="text-xs font-medium text-gray-700">Company ID</label>
              <div className="mt-1 flex gap-2">
                <input
                  value={companyId}
                  onChange={(e) => setCompanyId(e.target.value)}
                  placeholder="Enter Company ID"
                  className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                />
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
                  Auto-match
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

          {/* Column: Notes & actions */}
          <div className="space-y-3 md:col-span-1">
            <div>
              <label className="text-xs font-medium text-gray-700">Notes</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={5}
                placeholder="Add any notes here"
                className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleSave}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Save
              </button>
              <button
                onClick={() => {
                  handleSave();
                  onNext();
                }}
                className="inline-flex items-center gap-2 rounded-xl border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50"
              >
                Save & Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/***********************************
 * Main Component
 ***********************************/
export default function RejectedProducts({ projectId }: RejectedProductsProps) {
  const [products, setProducts] = useState<RejectedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [uploadingPdf, setUploadingPdf] = useState<number | null>(null);
  const [uploadingZip, setUploadingZip] = useState(false);
  
  // Supplier-related state
  const [suppliers, setSuppliers] = useState<SupplierData[]>([]);
  const [supplierMapping, setSupplierMapping] = useState<SupplierMappingSummary | null>(null);
  const [supplierMatchResult, setSupplierMatchResult] = useState<SupplierMatchResult | null>(null);
  const [uploadingSuppliers, setUploadingSuppliers] = useState(false);
  const [matchingSuppliers, setMatchingSuppliers] = useState(false);
  const [applyingMatches, setApplyingMatches] = useState(false);
  const [activeTab, setActiveTab] = useState<'products' | 'supplier-mapping'>('products');
  
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
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Download failed');
      }
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
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
        const downloadUrl = `/api/projects/${projectId}/rejected-products/download/${res.data.filename}`;
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
        const downloadUrl = `/api/projects/${projectId}/rejected-products/download/${res.data.zip_filename}`;
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


  const filtered = useMemo(() => filterProductsByQuery(products, query), [products, query]);

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

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('products')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'products'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Products
          </button>
          <button
            onClick={() => setActiveTab('supplier-mapping')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'supplier-mapping'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Supplier Mapping
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'products' && (
        <>
          <TopActions onExportCompleted={exportCompleted} onExportWorklist={exportWorklist} />

          {/* Bulk PDF Upload */}
          <div className="bg-white rounded-xl border p-4 mb-6">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <h3 className="font-semibold mb-2">Bulk PDF Upload</h3>
                <p className="text-sm text-gray-600 mb-3">
                  Upload a ZIP file with PDFs. The system will try to auto-assign PDFs to products based on filename matching.
                </p>
                <input
                  type="file"
                  accept=".zip"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadZip(file);
                  }}
                  disabled={uploadingZip}
                  className="text-sm"
                />
              </div>
              {uploadingZip && (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2 rounded-xl border bg-white px-3 py-2 shadow-sm">
              <div className="h-4 w-4 text-gray-400">🔍</div>
              <input 
                value={query} 
                onChange={(e) => setQuery(e.target.value)} 
                placeholder="Search products…" 
                className="w-64 text-sm outline-none" 
              />
            </div>
            <div className="text-sm text-gray-500">{filtered.length} products</div>
          </div>

          <div className="grid gap-4">
            {filtered.map((product, idx) => (
              <ProductRow 
                key={product.id} 
                product={product} 
                index={idx} 
                onSave={(data) => updateProduct(product.id, data)}
                onNext={() => console.log("next")}
                onUploadPdf={uploadPdf}
                onUpdateProduct={updateProduct}
                uploadingPdf={uploadingPdf}
              />
            ))}
          </div>
        </>
      )}

      {activeTab === 'supplier-mapping' && (
        <div className="space-y-6">
          {/* Supplier CSV Upload */}
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <h3 className="font-semibold mb-2">Upload Suppliers CSV</h3>
                <p className="text-sm text-gray-600 mb-3">
                  Upload a CSV file with supplier data. Required columns:
                </p>
                <div className="bg-gray-50 p-3 rounded-lg mb-3 text-sm">
                  <div className="font-medium mb-1">CSV Format:</div>
                  <div>• <strong>Supplier name</strong> - Name of the supplier/company</div>
                  <div>• <strong>CompanyID</strong> - Company identifier</div>
                  <div>• <strong>Country</strong> - Country/market code</div>
                  <div>• <strong>Total</strong> - Number of products (optional, defaults to 0)</div>
                </div>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadSuppliersCSV(file);
                  }}
                  disabled={uploadingSuppliers}
                  className="text-sm"
                />
              </div>
              {uploadingSuppliers && (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              )}
            </div>
          </div>

          {/* Supplier Mapping Summary */}
          {supplierMapping && (
            <div className="bg-white rounded-xl border p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Supplier Mapping Summary</h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={runSupplierMatching}
                    disabled={matchingSuppliers || suppliers.length === 0}
                    className="px-4 py-2 bg-blue-100 text-blue-800 border border-blue-200 rounded hover:bg-blue-200 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {matchingSuppliers ? "Matching..." : "Run AI Matching"}
                  </button>
                  {supplierMatchResult && (
                    <button
                      onClick={applySupplierMatches}
                      disabled={applyingMatches}
                      className="px-4 py-2 bg-green-100 text-green-800 border border-green-200 rounded hover:bg-green-200 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {applyingMatches ? "Applying..." : "Apply Matches"}
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <div className="text-2xl font-bold text-gray-800">{supplierMapping.supplier_summary.length}</div>
                  <div className="text-sm text-gray-600">Unique Suppliers</div>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <div className="text-2xl font-bold text-gray-800">{supplierMapping.total_unmatched_products}</div>
                  <div className="text-sm text-gray-600">Total Products</div>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                  <div className="text-2xl font-bold text-gray-800">{suppliers.length}</div>
                  <div className="text-sm text-gray-600">CSV Suppliers</div>
                </div>
              </div>

              {/* Supplier List */}
              <div className="space-y-3">
                <h4 className="font-medium">Suppliers without matches:</h4>
                {supplierMapping.supplier_summary.map((supplier, index) => (
                  <div key={index} className="border rounded-lg p-3 bg-gray-50">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium">{supplier.supplier_name}</div>
                        <div className="text-sm text-gray-600">Country: {supplier.country} • Products: {supplier.product_count}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Matching Results */}
          {supplierMatchResult && (
            <div className="bg-white rounded-xl border p-4">
              <h3 className="font-semibold mb-4">AI Matching Results</h3>
              
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
      )}
    </div>
  );
}