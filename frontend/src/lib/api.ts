import axios from "axios";

const api = axios.create({
  baseURL: "https://csv-mapping-backend-stagning-experimental.up.railway.app/api",
});

export default api;

export type DatabaseListItem = { id: number; name: string; filename: string; created_at: string; updated_at: string; };
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
