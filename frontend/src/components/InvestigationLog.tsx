// The visible reasoning: every search and document read the agent made, filled in live as events arrive.
import type { Investigation } from '../investigationState'
import { isRunning } from '../investigationState'

const MILLISECONDS_PER_SECOND = 1000

export function InvestigationLog({ investigation }: { investigation: Investigation }) {
  const isStillRunning = isRunning(investigation)
  const hasPendingStep = investigation.steps.some((step) => step.resultSummary === null)
  const removedCitationNotes = investigation.answer?.notes.length ?? 0
  const failedBeforeAnyStep = !isStillRunning && investigation.steps.length === 0 && !investigation.answer
  if (failedBeforeAnyStep) {
    return null // nothing to show; the error message below explains what happened
  }

  return (
    <details className="log" open>
      <summary className="log-summary">
        <span>Investigation</span>
        <span className="log-meta">{describeProgress(investigation)}</span>
      </summary>
      <ol className="log-steps" aria-live="polite">
        {investigation.steps.map((step, stepIndex) => (
          <li key={stepIndex} className={`log-step ${step.error ? 'log-step--failed' : ''}`}>
            <span className={`log-dot ${step.resultSummary === null ? 'log-dot--pending' : ''}`} aria-hidden="true" />
            <span className="log-description" title={step.foundTitles.join(' · ') || undefined}>
              {step.description}
            </span>
            <span className="log-result">{step.error ?? step.resultSummary ?? 'running…'}</span>
          </li>
        ))}
        {isStillRunning && !hasPendingStep && (
          <li className="log-step">
            <span className="log-dot log-dot--pending" aria-hidden="true" />
            <span className="log-description">
              {investigation.steps.length === 0 ? 'Planning the investigation' : 'Writing and checking the answer'}
            </span>
            <span className="log-result">running…</span>
          </li>
        )}
        {investigation.answer?.should_abstain && (
          <li className="log-step">
            <span className="log-dot log-dot--declined" aria-hidden="true" />
            <span className="log-description">Looked for supporting passages</span>
            <span className="log-result">none found · declined</span>
          </li>
        )}
        {investigation.answer && !investigation.answer.should_abstain && (
          <li className="log-step">
            <span
              className={`log-dot ${investigation.answer.conflicts.length > 0 ? 'log-dot--conflict' : ''}`}
              aria-hidden="true"
            />
            <span className="log-description">Checked every citation against the retrieved passages</span>
            <span className="log-result">
              {describeCheck(investigation.answer.conflicts.length, removedCitationNotes)}
            </span>
          </li>
        )}
      </ol>
    </details>
  )
}

// Counts what the agent did, by kind ("2 searches · 1 read"), so the header matches the rows below it.
function describeProgress(investigation: Investigation): string {
  const searchCount = investigation.steps.filter((step) => step.tool === 'search_documents').length
  const readCount = investigation.steps.filter((step) => step.tool === 'read_document').length
  const parts = [searchCount === 1 ? '1 search' : `${searchCount} searches`]
  if (readCount > 0) {
    parts.push(readCount === 1 ? '1 read' : `${readCount} reads`)
  }
  if (investigation.finishedAt === null) {
    return `${parts.join(' · ')} so far`
  }
  const seconds = (investigation.finishedAt - investigation.startedAt) / MILLISECONDS_PER_SECOND
  return `${parts.join(' · ')} · ${seconds.toFixed(1)} s`
}

function describeCheck(conflictCount: number, noteCount: number): string {
  const parts: string[] = []
  if (conflictCount > 0) {
    parts.push(conflictCount === 1 ? '1 conflict' : `${conflictCount} conflicts`)
  }
  if (noteCount > 0) {
    parts.push(noteCount === 1 ? '1 note' : `${noteCount} notes`)
  }
  return parts.length > 0 ? parts.join(' · ') : 'all supported'
}
