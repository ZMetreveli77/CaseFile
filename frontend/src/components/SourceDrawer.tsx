// Slides in from the right with the full passage behind a citation, so a claim can be checked in place.
import { useEffect, useRef, useState } from 'react'
import { fetchSourcePassage } from '../api'
import type { SourcePassage } from '../types'
import { Icon } from './Icon'

interface SourceDrawerProps {
  chunkId: string
  onClose: () => void
}

export function SourceDrawer({ chunkId, onClose }: SourceDrawerProps) {
  const [passage, setPassage] = useState<SourcePassage | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let isCurrentRequest = true // ignore a slow answer for a passage the user already moved away from
    setPassage(null)
    setErrorMessage(null)
    fetchSourcePassage(chunkId)
      .then((loadedPassage) => isCurrentRequest && setPassage(loadedPassage))
      .catch((error: Error) => isCurrentRequest && setErrorMessage(error.message))
    return () => {
      isCurrentRequest = false
    }
  }, [chunkId])

  useEffect(() => {
    closeButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const sourceFormat = typeof passage?.metadata.format === 'string' ? passage.metadata.format : null

  return (
    <aside className="drawer" aria-label="Source passage">
      <div className="drawer-head">
        <h2 className="drawer-title">{passage ? passage.title || passage.doc_id : 'Source passage'}</h2>
        <button ref={closeButtonRef} type="button" className="icon-button" onClick={onClose} aria-label="Close source">
          <Icon name="close" />
        </button>
      </div>
      {errorMessage && <p className="error-text">{errorMessage}</p>}
      {!passage && !errorMessage && <p className="muted">Loading passage…</p>}
      {passage && (
        <article>
          <p className="drawer-meta">
            Passage {passage.index + 1} of document <code>{passage.doc_id}</code>
            {sourceFormat && ` · ${sourceFormat}`}
          </p>
          <p className="drawer-text">{passage.text}</p>
        </article>
      )}
    </aside>
  )
}
