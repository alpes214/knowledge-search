export type DocStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface DocumentOut {
  id: string;
  filename: string;
  status: DocStatus;
  page_count: number | null;
  chunk_count: number | null;
  error_message: string | null;
  uploaded_at: string;
}

export interface UploadResponse {
  doc_id: string;
  status: DocStatus;
}

export interface SearchResult {
  chunk_id: number;
  document_id: string;
  filename: string;
  page: number | null;
  heading: string | null;
  text: string;
  score: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface Citation {
  n: number;
  chunk_id: number;
  document_id: string;
  filename: string;
  page: number | null;
  heading: string | null;
}

export interface ChunkRef {
  chunk_id: number;
  document_id: string;
  filename: string;
  page: number | null;
  heading: string | null;
  text: string;
  score: number;
}

export type AgentEvent =
  | { type: 'text'; delta: string }
  | { type: 'tool_use'; id: string; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; id: string; result: string; chunks: ChunkRef[] }
  | { type: 'done'; answer: string; citations: Citation[] }
  | { type: 'error'; code: string; detail: string; retriable: boolean };
