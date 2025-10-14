import axios from "axios";

// Force Railway deployment update

// Smart environment detection
const getBaseURL = () => {
  // Check if we're on experimental environment
  if (window.location.hostname.includes('stagning-experimental')) {
    return "https://csv-mapping-backend-stagning-experimental.up.railway.app/api";
  }
  
  // Check if we're running locally
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return "http://localhost:8000/api";
  }
  
  // Check environment variable first
  const envURL = (import.meta as any).env?.VITE_API_BASE;
  if (envURL) {
    return envURL;
  }
  
  // Default to production
  return "https://csv-mapping-production.up.railway.app/api";
};

const api = axios.create({
  baseURL: getBaseURL(),
});

export default api;

// AI Queue Status functions
export const getAIQueueStatus = async (projectId: number): Promise<AIQueueStatus> => {
  const response = await api.get(`/projects/${projectId}/ai/queue-status`);
  return response.data;
};

export const getUnifiedAIStatus = async (projectId: number): Promise<UnifiedAIStatus> => {
  const response = await api.get(`/projects/${projectId}/ai/unified-status`);
  return response.data;
};

export type DatabaseListItem = { id: number; name: string; filename: string; row_count: number; created_at: string; updated_at: string; };
export type Project = { id: number; name: string; status: string; active_database_id?: number | null; };
export type ImportUploadResponse = { import_file_id: number; filename: string; row_count: number; columns_map_json: Record<string, string>; };
export type MatchResultItem = {
  id: number;
  customer_row_index: number;
  decision: string;
  overall_score: number;
  reason: string;
  exact_match: boolean;
  customer_preview: Record<string, string>;
  db_preview?: Record<string, string> | null;
  ai_confidence?: number | null;
  // Supplier mapping data for rejected products
  mapped_supplier_name?: string | null;
  mapped_company_id?: string | null;
};
export type AiSuggestionItem = {
  id?: number;
  customer_row_index: number; rank: number; database_fields_json: Record<string, string>; confidence: number; rationale: string; source: string;
};

export type SupplierData = {
  id: number;
  supplier_name: string;
  company_id: string;
  country: string;
  total: number;
  created_at: string;
};

export type SupplierMappingSummary = {
  supplier_summary: Array<{
    supplier_name: string;
    country: string;
    product_count: number;
    products: Array<{
      id: number;
      customer_row_index: number;
      decision: string;
      reason: string;
    }>;
  }>;
  unmatched_suppliers: Array<{
    supplier_name: string;
    product_count: number;
    products: Array<{
      id: number;
      customer_row_index: number;
      decision: string;
      reason: string;
    }>;
  }>;
  total_unmatched_products: number;
};

export type SupplierMatchResult = {
  matched_suppliers: Array<{
    supplier_name: string;
    country: string;
    matched_supplier: SupplierData;
    match_type: string;
    products_affected: number;
  }>;
  new_country_needed: Array<{
    supplier_name: string;
    current_country: string;
    matched_supplier: SupplierData;
    products_affected: number;
  }>;
  new_supplier_needed: Array<{
    supplier_name: string;
    country: string;
    products_affected: number;
  }>;
  summary: {
    total_matched: number;
    new_country_needed: number;
    new_supplier_needed: number;
  };
};

export type AIQueueStatus = {
  queued: number;
  processing: number;
  ready: number;
  autoApproved: number;
};

export type UnifiedAIStatus = {
  csv: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  pdf: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  url: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  total: {
    queued: number;
    processing: number;
    completed: number;
    total: number;
  };
  hasActivity: boolean;
};
