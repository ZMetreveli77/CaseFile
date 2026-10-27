// Reads POST /ask/stream. The browser's EventSource only supports GET, so we read the Server-Sent Events
// ourselves: fetch the response, read its body chunk by chunk, and cut it into events.
//
// One event on the wire (see backend/casefile/api/streaming.py):
//   event: tool_call
//   data: {"type": "tool_call", ...}
//   <blank line>
// A line starting with ":" is a keep-alive comment and is ignored.
import { ApiError } from './api'
import type { InvestigationEvent } from './types'

const EVENT_SEPARATOR = '\n\n'

export async function streamInvestigation(
  question: string,
  onEvent: (event: InvestigationEvent) => void,
  abortSignal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
    signal: abortSignal,
  })
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, await describeFailedResponse(response))
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let unfinishedText = '' // a network chunk can end in the middle of an event

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    unfinishedText += decoder.decode(value, { stream: true })
    let separatorIndex = unfinishedText.indexOf(EVENT_SEPARATOR)
    while (separatorIndex !== -1) {
      const eventText = unfinishedText.slice(0, separatorIndex)
      unfinishedText = unfinishedText.slice(separatorIndex + EVENT_SEPARATOR.length)
      const event = parseEvent(eventText)
      if (event) {
        onEvent(event)
      }
      separatorIndex = unfinishedText.indexOf(EVENT_SEPARATOR)
    }
  }
}

// Only the "data:" line matters: the backend repeats the event name inside the JSON as "type".
export function parseEvent(eventText: string): InvestigationEvent | null {
  const dataLines = eventText
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trim())
  if (dataLines.length === 0) {
    return null // a keep-alive comment
  }
  return JSON.parse(dataLines.join('\n')) as InvestigationEvent
}

async function describeFailedResponse(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') {
      return body.detail
    }
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      return body.detail[0].msg
    }
  } catch {
    // not JSON
  }
  return `The investigation could not start (${response.status}).`
}
