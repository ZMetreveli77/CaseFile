// The Ask screen: every question asked in this visit, each with its live investigation and answer,
// and the question box pinned to the bottom.
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { describeInvestigationError } from '../errorMessages'
import type { Investigation } from '../investigationState'
import { AnswerView } from './AnswerView'
import { Icon } from './Icon'
import { InvestigationLog } from './InvestigationLog'

const MAX_QUESTION_CHARACTERS = 1000 // same limit as the backend (AskRequest in api/app.py)

interface AskViewProps {
  investigations: Investigation[]
  isInvestigating: boolean
  onAsk: (question: string) => void
  onRetry: (question: string) => void
  onOpenSource: (chunkId: string) => void
}

export function AskView({ investigations, isInvestigating, onAsk, onRetry, onOpenSource }: AskViewProps) {
  const [questionText, setQuestionText] = useState('')
  const threadEndRef = useRef<HTMLDivElement>(null)
  const latestInvestigation = investigations[investigations.length - 1]

  // Keep the newest step or answer in view while it streams in.
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: 'end' })
  }, [latestInvestigation])

  const submitQuestion = (event?: FormEvent) => {
    event?.preventDefault()
    const question = questionText.trim()
    if (!question || isInvestigating) {
      return
    }
    onAsk(question)
    setQuestionText('')
  }

  // Enter asks, Shift+Enter adds a new line.
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault() // otherwise the browser still types a new line into the emptied box
      submitQuestion()
    }
  }

  return (
    <div className="ask-view">
      <div className="thread">
        {investigations.length === 0 && (
          <div className="intro">
            <h1 className="intro-title">Ask a question about the documents</h1>
            <p>
              CaseFile searches the collection step by step, shows each search as it happens, and answers only with
              what the passages support. Every claim links to its source. When sources disagree it says so, and
              when the evidence is missing it declines instead of guessing.
            </p>
            <p className="muted">Try one of the questions on the left to see each of these.</p>
          </div>
        )}

        {investigations.map((investigation) => (
          <article key={investigation.id} className="exchange">
            <p className="question-bubble">{investigation.question}</p>
            <InvestigationLog investigation={investigation} />
            {investigation.answer && <AnswerView answer={investigation.answer} onOpenSource={onOpenSource} />}
            {investigation.errorMessage && (
              <div className="failure" role="alert">
                <FailureMessage detail={investigation.errorMessage} />
                <button
                  type="button"
                  className="button button--secondary"
                  disabled={isInvestigating}
                  onClick={() => onRetry(investigation.question)}
                >
                  Try again
                </button>
              </div>
            )}
          </article>
        ))}
        <div ref={threadEndRef} />
      </div>

      <div className="ask-dock">
        <form className="ask-box" onSubmit={submitQuestion}>
          <label htmlFor="question" className="visually-hidden">Question</label>
          <textarea
            id="question"
            className="ask-input"
            rows={1}
            maxLength={MAX_QUESTION_CHARACTERS}
            placeholder="Ask a question about the documents…"
            value={questionText}
            onChange={(event) => setQuestionText(event.target.value)}
            onKeyDown={submitOnEnter}
          />
          {/* Only disabled while busy: an empty question is ignored by submitQuestion, and a grey button reads as broken. */}
          <button type="submit" className="button" disabled={isInvestigating}>
            <Icon name="search" size={16} />
            {isInvestigating ? 'Investigating…' : 'Investigate'}
          </button>
        </form>
      </div>
    </div>
  )
}

function FailureMessage({ detail }: { detail: string }) {
  const { headline, technicalDetail } = describeInvestigationError(detail)
  return (
    <div className="failure-message">
      <p className="failure-headline">{headline}</p>
      {technicalDetail && (
        <details className="failure-detail">
          <summary><Icon name="chevronRight" size={14} />Technical details</summary>
          <p>{technicalDetail}</p>
        </details>
      )}
    </div>
  )
}
