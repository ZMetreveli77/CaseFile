// The Documents screen: upload files, page through what is indexed, replace or delete a document.
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import {
  deleteDocument, fetchSupportedFormats, listDocuments, replaceDocument, uploadDocument,
} from '../api'
import type { DocumentSummary, IngestResult, SupportedFormats } from '../types'
import { Icon } from './Icon'

const BYTES_PER_MEGABYTE = 1024 * 1024

// What each upload status means to the person who uploaded the file.
const STATUS_DESCRIPTIONS: Record<IngestResult['status'], string> = {
  added: 'Added',
  updated: 'Updated (same file name, new content)',
  unchanged: 'Unchanged (identical content already indexed)',
  duplicate: 'Skipped (duplicate of another document)',
}

interface UploadMessage {
  fileName: string
  text: string
  isError: boolean
}

export function DocumentsView() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [totalDocuments, setTotalDocuments] = useState<number | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [supportedFormats, setSupportedFormats] = useState<SupportedFormats | null>(null)
  const [uploadMessages, setUploadMessages] = useState<UploadMessage[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [documentPendingDelete, setDocumentPendingDelete] = useState<string | null>(null)
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const replaceInputRef = useRef<HTMLInputElement>(null)
  const documentToReplaceRef = useRef<string | null>(null)

  const loadFirstPage = useCallback(async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const page = await listDocuments(null)
      setDocuments(page.documents)
      setNextCursor(page.next_cursor)
      setTotalDocuments(page.total)
    } catch (error) {
      setLoadError((error as Error).message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFirstPage()
    fetchSupportedFormats().then(setSupportedFormats).catch(() => setSupportedFormats(null))
  }, [loadFirstPage])

  const loadNextPage = async () => {
    if (!nextCursor) {
      return
    }
    setIsLoading(true)
    try {
      const page = await listDocuments(nextCursor)
      setDocuments((loadedDocuments) => [...loadedDocuments, ...page.documents])
      setNextCursor(page.next_cursor)
    } catch (error) {
      setLoadError((error as Error).message)
    } finally {
      setIsLoading(false)
    }
  }

  const uploadSelectedFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = [...(event.target.files ?? [])]
    event.target.value = '' // so choosing the same file again still fires a change
    if (files.length === 0) {
      return
    }
    setIsUploading(true)
    const messages: UploadMessage[] = []
    for (const file of files) {
      try {
        const results = await uploadDocument(file)
        messages.push({ fileName: file.name, text: summarizeUpload(results), isError: false })
      } catch (error) {
        messages.push({ fileName: file.name, text: (error as Error).message, isError: true })
      }
    }
    setUploadMessages(messages)
    setIsUploading(false)
    loadFirstPage()
  }

  const startReplace = (documentId: string) => {
    documentToReplaceRef.current = documentId
    replaceInputRef.current?.click()
  }

  const replaceWithSelectedFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    const documentId = documentToReplaceRef.current
    event.target.value = ''
    if (!file || !documentId) {
      return
    }
    setBusyDocumentId(documentId)
    try {
      const result = await replaceDocument(documentId, file)
      setUploadMessages([{ fileName: file.name, text: `${STATUS_DESCRIPTIONS[result.status]}: ${result.title}`, isError: false }])
      loadFirstPage()
    } catch (error) {
      setUploadMessages([{ fileName: file.name, text: (error as Error).message, isError: true }])
    } finally {
      setBusyDocumentId(null)
    }
  }

  const confirmDelete = async (documentId: string) => {
    setBusyDocumentId(documentId)
    try {
      await deleteDocument(documentId)
      setDocuments((loadedDocuments) => loadedDocuments.filter((document) => document.doc_id !== documentId))
      setTotalDocuments((total) => (total === null ? total : total - 1))
    } catch (error) {
      setLoadError((error as Error).message)
    } finally {
      setBusyDocumentId(null)
      setDocumentPendingDelete(null)
    }
  }

  const acceptedExtensions = supportedFormats?.extensions.join(',')
  const maxUploadMegabytes = supportedFormats ? supportedFormats.max_upload_bytes / BYTES_PER_MEGABYTE : null

  return (
    <div className="documents-view">
      <header className="documents-head">
        <div>
          <h1 className="page-title">Documents</h1>
          <p className="muted">
            {totalDocuments === null ? 'Loading…' : `${totalDocuments.toLocaleString('en-US')} documents indexed`}
          </p>
        </div>
        <div className="upload">
          <button
            type="button"
            className="button"
            disabled={isUploading}
            onClick={() => uploadInputRef.current?.click()}
          >
            <Icon name="upload" size={16} />
            {isUploading ? 'Uploading…' : 'Upload files'}
          </button>
          {supportedFormats && (
            <p className="upload-hint">
              {supportedFormats.extensions.join(' ')} · up to {maxUploadMegabytes} MB each
            </p>
          )}
        </div>
        <input
          ref={uploadInputRef}
          type="file"
          multiple
          accept={acceptedExtensions}
          className="visually-hidden"
          onChange={uploadSelectedFiles}
          aria-label="Choose files to upload"
        />
        <input
          ref={replaceInputRef}
          type="file"
          accept={acceptedExtensions}
          className="visually-hidden"
          onChange={replaceWithSelectedFile}
          aria-label="Choose a replacement file"
        />
      </header>

      {uploadMessages.length > 0 && (
        <ul className="upload-messages" role="status">
          {uploadMessages.map((message) => (
            <li key={message.fileName} className={message.isError ? 'upload-message--error' : ''}>
              <strong>{message.fileName}</strong>: {message.text}
            </li>
          ))}
        </ul>
      )}

      {loadError && (
        <div className="failure" role="alert">
          <p>{loadError}</p>
          <button type="button" className="button button--secondary" onClick={loadFirstPage}>Try again</button>
        </div>
      )}

      <div className="table-wrap">
        <table className="documents-table">
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">Format</th>
              <th scope="col">Document id</th>
              <th scope="col"><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.doc_id}>
                <td className="document-title">{document.title}</td>
                <td>{document.metadata.format ?? '—'}</td>
                <td><code>{document.doc_id}</code></td>
                <td className="row-actions">
                  {documentPendingDelete === document.doc_id ? (
                    <>
                      <button
                        type="button"
                        className="button button--danger button--small"
                        disabled={busyDocumentId === document.doc_id}
                        onClick={() => confirmDelete(document.doc_id)}
                      >
                        Delete for good
                      </button>
                      <button
                        type="button"
                        className="button button--secondary button--small"
                        onClick={() => setDocumentPendingDelete(null)}
                      >
                        Keep
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="icon-button"
                        disabled={busyDocumentId === document.doc_id}
                        onClick={() => startReplace(document.doc_id)}
                        aria-label={`Replace ${document.title}`}
                        title="Replace with a new file"
                      >
                        <Icon name="replace" />
                      </button>
                      <button
                        type="button"
                        className="icon-button icon-button--danger"
                        onClick={() => setDocumentPendingDelete(document.doc_id)}
                        aria-label={`Delete ${document.title}`}
                        title="Delete"
                      >
                        <Icon name="trash" />
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && documents.length === 0 && !loadError && (
          <p className="empty">No documents yet. Upload a PDF, text, HTML, JSON or CSV file to start.</p>
        )}
      </div>

      {nextCursor && (
        <button type="button" className="button button--secondary load-more" disabled={isLoading} onClick={loadNextPage}>
          {isLoading ? 'Loading…' : 'Load more'}
        </button>
      )}
    </div>
  )
}

function summarizeUpload(results: IngestResult[]): string {
  if (results.length === 1) {
    return `${STATUS_DESCRIPTIONS[results[0].status]}, ${results[0].chunks} passages`
  }
  const addedCount = results.filter((result) => result.status === 'added' || result.status === 'updated').length
  return `${results.length} documents in the file, ${addedCount} added or updated`
}
