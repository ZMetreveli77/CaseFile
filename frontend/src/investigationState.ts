// What the UI knows about one question while it is being investigated, and how each stream event changes it.
// applyInvestigationEvent is a pure function (old state + event -> new state), so it is easy to test.
import type { InvestigationAnswer, InvestigationEvent } from './types'

export interface InvestigationStep {
  tool: string // search_documents | read_document
  description: string // e.g. 'Searched "La Voz del Pueblo"'
  resultSummary: string | null // null while the tool is still running
  foundTitles: string[]
  error: string | null
}

export interface Investigation {
  id: number
  question: string
  steps: InvestigationStep[]
  answer: InvestigationAnswer | null
  errorMessage: string | null
  startedAt: number // milliseconds, from Date.now()
  finishedAt: number | null
}

export function createInvestigation(id: number, question: string): Investigation {
  return { id, question, steps: [], answer: null, errorMessage: null, startedAt: Date.now(), finishedAt: null }
}

export function isRunning(investigation: Investigation): boolean {
  return investigation.finishedAt === null
}

export function applyInvestigationEvent(investigation: Investigation, event: InvestigationEvent): Investigation {
  switch (event.type) {
    case 'started':
      return investigation
    case 'tool_call':
      return { ...investigation, steps: [...investigation.steps, describeToolCall(event.tool, event.arguments)] }
    case 'tool_result':
      return { ...investigation, steps: completeLastStep(investigation.steps, event.titles, event.error) }
    case 'answer': {
      const { type: _eventType, ...answer } = event
      return { ...investigation, answer, finishedAt: Date.now() }
    }
    case 'error':
      return failInvestigation(investigation, event.detail)
  }
}

export function failInvestigation(investigation: Investigation, errorMessage: string): Investigation {
  return { ...investigation, errorMessage, finishedAt: Date.now() }
}

function describeToolCall(tool: string, toolArguments: Record<string, unknown>): InvestigationStep {
  let description = `Used ${tool}`
  if (tool === 'search_documents') {
    description = `Searched “${String(toolArguments.query ?? '')}”`
  } else if (tool === 'read_document') {
    description = `Read document ${String(toolArguments.doc_id ?? '')}`
  }
  return { tool, description, resultSummary: null, foundTitles: [], error: null }
}

function completeLastStep(steps: InvestigationStep[], titles: string[], error: string | null): InvestigationStep[] {
  if (steps.length === 0) {
    return steps
  }
  const lastStep = steps[steps.length - 1]
  const completedStep: InvestigationStep = { ...lastStep, foundTitles: titles, error }
  if (error) {
    completedStep.resultSummary = 'failed'
  } else if (lastStep.tool === 'read_document') {
    completedStep.description = titles[0] ? `Read “${titles[0]}”` : lastStep.description
    completedStep.resultSummary = '1 document'
  } else {
    completedStep.resultSummary = titles.length === 1 ? '1 result' : `${titles.length} results`
  }
  return [...steps.slice(0, -1), completedStep]
}

// Citations get numbers in order of first appearance (claims first, then conflicts), like footnotes.
export function numberCitations(answer: InvestigationAnswer): Map<string, number> {
  const citationNumbers = new Map<string, number>()
  const allCitations = [
    ...answer.claims.flatMap((claim) => claim.citations),
    ...answer.conflicts.flatMap((conflict) => conflict.citations),
  ]
  for (const chunkId of allCitations) {
    if (!citationNumbers.has(chunkId)) {
      citationNumbers.set(chunkId, citationNumbers.size + 1)
    }
  }
  return citationNumbers
}
