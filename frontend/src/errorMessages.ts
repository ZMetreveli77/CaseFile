// Turns a backend error detail into a short sentence a visitor can act on.
// The full provider text is kept as `technicalDetail`, shown only when asked for.
export interface FriendlyError {
  headline: string
  technicalDetail: string | null
}

const QUOTA_PATTERN = /\b429\b|quota/i
const UNAVAILABLE_PATTERN = /language model is unavailable|timed out|\b503\b/i
const WAIT_HOURS_PATTERN = /wait ([\d.]+) ?h/i // the backend's retry layer reports e.g. "asks to wait 6.4 h"

export function describeInvestigationError(detail: string): FriendlyError {
  if (QUOTA_PATTERN.test(detail)) {
    const waitHours = detail.match(WAIT_HOURS_PATTERN)?.[1]
    const whenToRetry = waitHours ? `in about ${Math.ceil(Number(waitHours))} hours` : 'later'
    return {
      headline: `The language model's free usage limit has been reached. Try again ${whenToRetry}.`,
      technicalDetail: detail,
    }
  }
  if (UNAVAILABLE_PATTERN.test(detail)) {
    return { headline: 'The language model is not responding right now. Try again in a minute.', technicalDetail: detail }
  }
  return { headline: detail, technicalDetail: null }
}
