import { describe, expect, it } from 'vitest'
import {
  applyInvestigationEvent, createInvestigation, isRunning, numberCitations, stopInvestigation,
} from './investigationState'
import { parseEvent } from './investigationStream'
import { describeInvestigationError } from './errorMessages'
import type { InvestigationAnswer } from './types'

const EMPTY_ANSWER: InvestigationAnswer = {
  question: 'q', answer: '', claims: [], conflicts: [], should_abstain: false, abstain_reason: '',
  search_queries: [], retrieved_chunk_ids: [], source_titles: {}, llm_calls: 1, notes: [],
}

describe('parseEvent', () => {
  it('reads the JSON on the data line', () => {
    const event = parseEvent('event: tool_call\ndata: {"type": "tool_call", "tool": "search_documents", "arguments": {}}')
    expect(event).toEqual({ type: 'tool_call', tool: 'search_documents', arguments: {} })
  })

  it('ignores keep-alive comments', () => {
    expect(parseEvent(': keep-alive')).toBeNull()
  })
})

describe('applyInvestigationEvent', () => {
  it('adds a step per tool call and completes it with the tool result', () => {
    let investigation = createInvestigation(1, 'Who built the hotel?')
    investigation = applyInvestigationEvent(investigation, {
      type: 'tool_call', tool: 'search_documents', arguments: { query: 'hotel builder' },
    })
    expect(investigation.steps[0]).toMatchObject({ description: 'Searched “hotel builder”', resultSummary: null })

    investigation = applyInvestigationEvent(investigation, {
      type: 'tool_result', tool: 'search_documents', titles: ['Hotel', 'Port Ellis'], error: null,
    })
    expect(investigation.steps[0].resultSummary).toBe('2 results')
    expect(isRunning(investigation)).toBe(true)
  })

  it('names the document once a read returns its title', () => {
    let investigation = createInvestigation(1, 'q')
    investigation = applyInvestigationEvent(investigation, { type: 'tool_call', tool: 'read_document', arguments: { doc_id: 'd1' } })
    investigation = applyInvestigationEvent(investigation, { type: 'tool_result', tool: 'read_document', titles: ['Hotel'], error: null })
    expect(investigation.steps[0]).toMatchObject({ description: 'Read “Hotel”', resultSummary: '1 document' })
  })

  it('finishes on an answer or an error', () => {
    const answered = applyInvestigationEvent(createInvestigation(1, 'q'), { type: 'answer', ...EMPTY_ANSWER })
    expect(isRunning(answered)).toBe(false)
    expect(answered.answer?.llm_calls).toBe(1)

    const failed = applyInvestigationEvent(createInvestigation(2, 'q'), { type: 'error', detail: 'quota exceeded' })
    expect(failed.errorMessage).toBe('quota exceeded')
    expect(isRunning(failed)).toBe(false)
  })
})

describe('numberCitations', () => {
  it('numbers sources by first appearance, claims before conflicts', () => {
    const numbers = numberCitations({
      ...EMPTY_ANSWER,
      claims: [{ text: 'a', citations: ['b:0'] }, { text: 'b', citations: ['a:0', 'b:0'] }],
      conflicts: [{ description: 'c', citations: ['c:0', 'a:0'] }],
    })
    expect([...numbers.entries()]).toEqual([['b:0', 1], ['a:0', 2], ['c:0', 3]])
  })
})

describe('describeInvestigationError', () => {
  it('turns a daily quota error into a short message with the wait time', () => {
    const friendly = describeInvestigationError(
      'The language model is unavailable: Gemini error 429: quota exceeded (the provider asks to wait 6.4 h)')
    expect(friendly.headline).toBe("The language model's free usage limit has been reached. Try again in about 7 hours.")
    expect(friendly.technicalDetail).toContain('429')
  })

  it('passes other messages through unchanged', () => {
    expect(describeInvestigationError('question must not be empty')).toEqual({
      headline: 'question must not be empty', technicalDetail: null,
    })
  })
})

describe('stopInvestigation', () => {
  it('ends the investigation as stopped and marks the step that was still running', () => {
    let investigation = createInvestigation(1, 'q')
    investigation = applyInvestigationEvent(investigation, { type: 'tool_call', tool: 'search_documents', arguments: { query: 'a' } })
    investigation = applyInvestigationEvent(investigation, { type: 'tool_result', tool: 'search_documents', titles: ['A'], error: null })
    investigation = applyInvestigationEvent(investigation, { type: 'tool_call', tool: 'search_documents', arguments: { query: 'b' } })

    const stopped = stopInvestigation(investigation)
    expect(isRunning(stopped)).toBe(false)
    expect(stopped.wasStopped).toBe(true)
    expect(stopped.errorMessage).toBeNull() // stopping is the visitor's choice, not an error
    expect(stopped.steps.map((step) => step.resultSummary)).toEqual(['1 result', 'stopped'])
  })
})
