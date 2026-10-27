// The finished answer: cited claims, conflicts between sources, or a plain refusal when evidence is missing.
import type { InvestigationAnswer } from '../types'
import { numberCitations } from '../investigationState'
import { Icon } from './Icon'
import { SourceCard } from './SourceCard'

interface AnswerViewProps {
  answer: InvestigationAnswer
  onOpenSource: (chunkId: string) => void
}

export function AnswerView({ answer, onOpenSource }: AnswerViewProps) {
  if (answer.should_abstain) {
    return (
      <div className="declined">
        <h3 className="declined-title">Not enough evidence to answer</h3>
        <p>{answer.abstain_reason || 'The documents do not contain what this question needs.'}</p>
        <p className="declined-detail">
          CaseFile searched {answer.search_queries.length === 1 ? 'once' : `${answer.search_queries.length} times`}
          {' '}and read {answer.retrieved_chunk_ids.length} passages, but none supported an answer.
        </p>
      </div>
    )
  }

  const citationNumbers = numberCitations(answer)
  const citedChunkIds = [...citationNumbers.keys()]
  const uncitedChunkIds = answer.retrieved_chunk_ids.filter((chunkId) => !citationNumbers.has(chunkId))
  const titleOf = (chunkId: string) => answer.source_titles[chunkId] ?? chunkId

  const renderCitation = (chunkId: string) => (
    <button
      key={chunkId}
      type="button"
      className="citation"
      onClick={() => onOpenSource(chunkId)}
      aria-label={`Source ${citationNumbers.get(chunkId)}: ${titleOf(chunkId)}`}
    >
      {citationNumbers.get(chunkId)}
    </button>
  )

  return (
    <div className="answer">
      {answer.claims.length > 0 ? (
        <p className="answer-text">
          {answer.claims.map((claim, claimIndex) => (
            <span key={claimIndex}>
              {claim.text}
              {claim.citations.map(renderCitation)}{' '}
            </span>
          ))}
        </p>
      ) : (
        <p className="answer-text">{answer.answer}</p>
      )}

      {answer.conflicts.map((conflict, conflictIndex) => (
        <section key={conflictIndex} className="conflict" aria-label="Sources conflict">
          <h3 className="conflict-title">Sources conflict</h3>
          {/* The backend sends a description, not the conflicting values, so the sources are linked by number. */}
          <p>
            {conflict.description} <span className="conflict-between">Between sources</span>
            {conflict.citations.map(renderCitation)}
          </p>
        </section>
      ))}

      {citedChunkIds.length > 0 && (
        <div className="source-cards">
          {citedChunkIds.map((chunkId) => (
            <SourceCard
              key={chunkId}
              chunkId={chunkId}
              citationNumber={citationNumbers.get(chunkId) ?? 0}
              title={titleOf(chunkId)}
              onOpen={onOpenSource}
            />
          ))}
        </div>
      )}

      {uncitedChunkIds.length > 0 && (
        <details className="uncited">
          <summary>
            <Icon name="chevronRight" size={14} />
            {uncitedChunkIds.length} more {uncitedChunkIds.length === 1 ? 'passage was' : 'passages were'} read
            but not cited
          </summary>
          <ul>
            {uncitedChunkIds.map((chunkId) => (
              <li key={chunkId}>
                <button type="button" className="link-button" onClick={() => onOpenSource(chunkId)}>
                  {titleOf(chunkId)}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {answer.notes.length > 0 && (
        <ul className="answer-notes" aria-label="Checks">
          {answer.notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </div>
  )
}
