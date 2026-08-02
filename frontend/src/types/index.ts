export interface TagInfo {
  id: number;
  name: string;
  color: string;
}

export interface Tag extends TagInfo {
  doc_count: number;
}

export interface Document {
  id: number;
  filename: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string | null;
  chunk_count: number;
  tags: TagInfo[];
}

export interface Source {
  file: string;
  page: number | null;
  snippet: string;
  doc_id: number | null;
  type?: 'document' | 'web';
  url?: string;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[] | null;
  created_at: string | null;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string | null;
  messages?: Message[];
}

export interface Settings {
  llm_base_url: string;
  llm_model_name: string;
  embedding_model_name: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  temperature: number;
  max_tokens: number;
  context_window: number;
  similarity_threshold: number;
  hybrid_search: boolean;
  bm25_weight: number;
  retrieval_top_k: number;
  rerank_top_k: number;
  rerank_enabled: boolean;
  rerank_threshold: number;
  query_rewrite_enabled: boolean;
  web_search_enabled: boolean;
}

export interface DocumentContent {
  id: number;
  filename: string;
  parsed_content: string;
  page_breaks: number[] | null;
  chunk_count: number;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string | null;
  created_at: string | null;
  doc_count: number;
}

export type BatchImportResult =
  | { url: string; status: 'pending'; id: number }
  | { url: string; status: 'skipped'; detail: string };

export interface BatchImportResponse {
  imported: number;
  results: BatchImportResult[];
}

export interface SSEBaseV1 { schema_version: 1 }
export interface SSEDoneV1 extends SSEBaseV1 { conversation_id: number }
