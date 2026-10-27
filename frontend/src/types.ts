// Shapes of the JSON the backend sends. They mirror the Python dataclasses in backend/casefile.

export interface Claim {
  text: string
  citations: string[] // chunk ids, e.g. "doc-42:0"
}

export interface Conflict {
  description: string
  citations: string[]
}

// Mirrors InvestigationAnswer in backend/casefile/rag/agent.py
export interface InvestigationAnswer {
  question: string
  answer: string
  claims: Claim[]
  conflicts: Conflict[]
  should_abstain: boolean
  abstain_reason: string
  search_queries: string[]
  retrieved_chunk_ids: string[]
  source_titles: Record<string, string> // chunk id -> document title
  llm_calls: number
  notes: string[] // e.g. citations the validator removed
}

// Events of POST /ask/stream, in the order they can arrive.
export type InvestigationEvent =
  | { type: 'started'; question: string }
  | { type: 'tool_call'; tool: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; titles: string[]; error: string | null }
  | ({ type: 'answer' } & InvestigationAnswer)
  | { type: 'error'; detail: string }

// One passage, as returned by GET /sources/{chunk_id}
export interface SourcePassage {
  chunk_id: string
  doc_id: string
  index: number
  text: string
  title: string
  metadata: Record<string, unknown>
}

// One row of GET /documents (the document text is left out)
export interface DocumentSummary {
  doc_id: string
  title: string
  content_hash: string
  metadata: { filename?: string; format?: string; [key: string]: unknown }
}

export interface DocumentPage {
  documents: DocumentSummary[]
  next_cursor: string | null
  total: number
}

// Mirrors IngestResult in backend/casefile/ingestion/pipeline.py
export interface IngestResult {
  doc_id: string
  title: string
  status: 'added' | 'updated' | 'unchanged' | 'duplicate'
  chunks: number
  duplicate_of: string | null
}

export interface HealthReport {
  status: 'ok' | 'degraded'
  model?: string
  documents?: number
  chunks?: number
  detail?: string
}

export interface SupportedFormats {
  extensions: string[]
  max_upload_bytes: number
}
