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
};
export type AiSuggestionItem = {
  id?: number;
  customer_row_index: number; rank: number; database_fields_json: Record<string, string>; confidence: number; rationale: string; source: string;
};
