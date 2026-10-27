// One cited source under the answer: its number, title and the start of the passage, so a reader can
// judge it before opening the full text in the drawer.
import { useEffect, useState } from 'react'
import { fetchSourcePassage } from '../api'

interface SourceCardProps {
  chunkId: string
  citationNumber: number
  title: string
  onOpen: (chunkId: string) => void
}

export function SourceCard({ chunkId, citationNumber, title, onOpen }: SourceCardProps) {
  const [passageText, setPassageText] = useState<string | null>(null)

  useEffect(() => {
    let isCurrentRequest = true
    fetchSourcePassage(chunkId)
      .then((passage) => isCurrentRequest && setPassageText(passage.text))
      .catch(() => isCurrentRequest && setPassageText(null)) // the card still works without the excerpt
    return () => {
      isCurrentRequest = false
    }
  }, [chunkId])

  return (
    <button type="button" className="source-card" onClick={() => onOpen(chunkId)}>
      <span className="source-card-number">{citationNumber}</span>
      <span className="source-card-title">{title}</span>
      <span className="source-card-excerpt">{passageText ?? 'Open passage'}</span>
    </button>
  )
}
