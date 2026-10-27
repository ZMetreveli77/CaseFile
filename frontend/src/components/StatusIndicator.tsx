// The dot at the foot of the sidebar: is the backend reachable, and how much is indexed?
// Render's free tier sleeps when idle, so a slow first answer gets its own "waking up" message.
import type { HealthReport } from '../types'

export type ConnectionState = 'connecting' | 'waking' | 'ready' | 'degraded' | 'offline'

interface StatusIndicatorProps {
  connectionState: ConnectionState
  health: HealthReport | null
}

export function StatusIndicator({ connectionState, health }: StatusIndicatorProps) {
  return (
    <div className="status" role="status" aria-live="polite">
      <span className={`status-dot status-dot--${connectionState}`} aria-hidden="true" />
      <span>{describeConnection(connectionState, health)}</span>
    </div>
  )
}

function describeConnection(connectionState: ConnectionState, health: HealthReport | null): string {
  switch (connectionState) {
    case 'connecting':
      return 'Connecting…'
    case 'waking':
      return 'Waking the server (free hosting sleeps when idle, up to a minute)…'
    case 'ready':
      return `Ready · ${(health?.documents ?? 0).toLocaleString('en-US')} documents`
    case 'degraded':
      return 'Database unreachable. Retrying…'
    case 'offline':
      return 'Server unreachable. Retrying…'
  }
}
