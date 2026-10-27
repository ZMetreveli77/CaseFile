// One function per backend endpoint. In development Vite forwards these paths to uvicorn (see vite.config.ts);
// in production FastAPI serves this app itself, so the same relative paths work in both.
import type {
  DocumentPage, HealthReport, IngestResult, SourcePassage, SupportedFormats,
} from './types'

const DOCUMENTS_PAGE_SIZE = 50

// Raised for any non-2xx response; `message` is the backend's "detail" text when there is one.
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function readJsonOrThrow<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>
  }
  let message = `Request failed (${response.status})`
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') {
      message = body.detail
    } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      message = body.detail[0].msg // FastAPI validation errors arrive as a list
    }
  } catch {
    // the body was not JSON; keep the generic message
  }
  throw new ApiError(response.status, message)
}

// /health answers 503 with a JSON body when the database is unreachable, so read the body either way.
export async function fetchHealth(): Promise<HealthReport> {
  const response = await fetch('/health')
  return response.json() as Promise<HealthReport>
}

export async function fetchSupportedFormats(): Promise<SupportedFormats> {
  return readJsonOrThrow(await fetch('/formats'))
}

export async function listDocuments(cursor: string | null): Promise<DocumentPage> {
  const query = new URLSearchParams({ limit: String(DOCUMENTS_PAGE_SIZE) })
  if (cursor) {
    query.set('cursor', cursor)
  }
  return readJsonOrThrow(await fetch(`/documents?${query}`))
}

export async function uploadDocument(file: File): Promise<IngestResult[]> {
  const form = new FormData()
  form.append('file', file)
  const body = await readJsonOrThrow<{ results: IngestResult[] }>(
    await fetch('/documents', { method: 'POST', body: form }),
  )
  return body.results
}

export async function replaceDocument(documentId: string, file: File): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  return readJsonOrThrow(await fetch(`/documents/${encodeURIComponent(documentId)}`, { method: 'PUT', body: form }))
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
  if (!response.ok) {
    await readJsonOrThrow(response) // throws with the backend's message
  }
}

export async function fetchSourcePassage(chunkId: string): Promise<SourcePassage> {
  return readJsonOrThrow(await fetch(`/sources/${encodeURIComponent(chunkId)}`))
}
