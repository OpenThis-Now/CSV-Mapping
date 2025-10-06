import React, { useEffect, useState } from "react";
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

export default function RejectedProducts({ projectId }: RejectedProductsProps) {
  const [products, setProducts] = useState<RejectedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProduct, setEditingProduct] = useState<number | null>(null);
  const [editData, setEditData] = useState<Partial<RejectedProduct>>({});
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
      setEditingProduct(null);
      setEditData({});
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

  const downloadFile = (url: string, filename: string) => {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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
        downloadFile(downloadUrl, res.data.filename);
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
        downloadFile(downloadUrl, res.data.zip_filename);
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
      showToast(res.data.message, 'success');
      await loadSuppliers();
      await loadSupplierMapping();
    } catch (error) {
      console.error("Failed to upload suppliers CSV:", error);
      showToast("Failed to upload suppliers CSV", 'error');
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

  const getStatusBadge = (status: string) => {
    const badges = {
      needs_data: "bg-yellow-100 text-yellow-800 border-yellow-300",
      complete: "bg-green-100 text-green-800 border-green-300",
      sent: "bg-blue-100 text-blue-800 border-blue-300",
      request_worklist: "bg-purple-100 text-purple-800 border-purple-300"
    };
    return badges[status as keyof typeof badges] || "bg-gray-100 text-gray-800 border-gray-300";
  };

  const getStatusText = (status: string) => {
    const texts = {
      needs_data: "Needs Data",
      complete: "Complete",
      sent: "Sent",
      request_worklist: "Request Worklist"
    };
    return texts[status as keyof typeof texts] || status;
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Rejected Products</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCompleted}
            className="px-4 py-2 bg-green-100 text-green-800 border border-green-200 rounded hover:bg-green-200 text-sm"
          >
            Export Completed (CSV)
          </button>
          <button
            onClick={exportWorklist}
            className="px-4 py-2 bg-purple-100 text-purple-800 border border-purple-200 rounded hover:bg-purple-200 text-sm"
          >
            Export Request Worklist (CSV + ZIP)
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
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
          {/* Bulk PDF Upload */}
          <div className="bg-white rounded-xl border p-4">
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

          {/* Products List */}
          <div className="grid gap-4">
            {products.map((product) => (
              <div key={product.id} className="bg-white rounded-xl border p-4">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-lg">{product.product_name}</h3>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium border ${getStatusBadge(product.status)}`}>
                        {getStatusText(product.status)}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600 mb-1">
                      <strong>Article Number:</strong> {product.article_number || 'N/A'}
                    </div>
                    <div className="text-sm text-gray-600 mb-1">
                      <strong>Supplier:</strong> {product.supplier}
                    </div>
                    <div className="text-sm text-gray-600 mb-1">
                      <strong>Reason:</strong> {product.reason}
                    </div>
                    {product.company_id && (
                      <div className="text-sm text-gray-600 mb-1">
                        <strong>Company ID:</strong> {product.company_id}
                      </div>
                    )}
                    {product.pdf_filename && (
                      <div className="text-sm text-gray-600 mb-1">
                        <strong>PDF:</strong> {product.pdf_filename}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      setEditingProduct(product.id);
                      setEditData({
                        company_id: product.company_id,
                        notes: product.notes,
                        status: product.status
                      });
                    }}
                    className="px-3 py-1 bg-blue-100 text-blue-800 rounded hover:bg-blue-200 text-sm"
                  >
                    Edit
                  </button>
                </div>

                {/* Edit Form */}
                {editingProduct === product.id && (
                  <div className="border-t pt-4 mt-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Company ID
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={editData.company_id || ''}
                            onChange={(e) => setEditData({...editData, company_id: e.target.value})}
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Enter Company ID"
                          />
                          <button
                            onClick={async () => {
                              showToast(`Auto-matching Company ID for supplier: ${product.supplier}`, 'info');
                              try {
                                // Trigger auto-matching by calling the backend endpoint
                                await api.post(`/projects/${projectId}/rejected-products/${product.id}/auto-match`);
                                showToast("Auto-matching completed", 'success');
                                await loadProducts();
                              } catch (error) {
                                console.error("Auto-match failed:", error);
                                showToast("Auto-matching failed", 'error');
                              }
                            }}
                            className="px-3 py-2 bg-blue-100 text-blue-800 rounded hover:bg-blue-200 text-sm"
                          >
                            Auto-match
                          </button>
                        </div>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Status
                        </label>
                        <select
                          value={editData.status || 'needs_data'}
                          onChange={(e) => setEditData({...editData, status: e.target.value as any})}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="needs_data">Needs Data</option>
                          <option value="complete">Complete</option>
                          <option value="sent">Sent</option>
                          <option value="request_worklist">Request Worklist</option>
                        </select>
                      </div>
                    </div>
                    <div className="mt-4">
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Notes
                      </label>
                      <textarea
                        value={editData.notes || ''}
                        onChange={(e) => setEditData({...editData, notes: e.target.value})}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                        rows={3}
                        placeholder="Add notes..."
                      />
                    </div>
                    <div className="mt-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Upload PDF
                      </label>
                      <input
                        type="file"
                        accept=".pdf"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) uploadPdf(product.id, file);
                        }}
                        disabled={uploadingPdf === product.id}
                        className="text-sm"
                      />
                      {uploadingPdf === product.id && (
                        <div className="mt-2 text-sm text-blue-600">Uploading...</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-4">
                      <button
                        onClick={() => updateProduct(product.id, editData)}
                        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                      >
                        Save Changes
                      </button>
                      <button
                        onClick={() => {
                          setEditingProduct(null);
                          setEditData({});
                        }}
                        className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
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
                  Upload a CSV file with supplier data. Required columns: Supplier name, CompanyID, Country, Total
                </p>
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
                  <h4 className="font-medium mb-3 text-green-800">✓ Exact Matches</h4>
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
                  <h4 className="font-medium mb-3 text-yellow-800">⚠ New Country Needed</h4>
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
                  <h4 className="font-medium mb-3 text-red-800">✗ New Supplier Needed</h4>
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
