// The whole app: sidebar on the left, the Ask or Documents screen on the right, and the source drawer on top.
// App owns the state that more than one component needs: investigations, health, theme, open source.
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchHealth } from './api'
import {
  applyInvestigationEvent, createInvestigation, failInvestigation, isRunning, type Investigation,
} from './investigationState'
import { streamInvestigation } from './investigationStream'
import { applyTheme, readSavedTheme, readSystemTheme, type Theme } from './theme'
import type { HealthReport } from './types'
import { AskView } from './components/AskView'
import { DocumentsView } from './components/DocumentsView'
import { Sidebar, type View } from './components/Sidebar'
import { SourceDrawer } from './components/SourceDrawer'
import type { ConnectionState } from './components/StatusIndicator'

const WAKING_THRESHOLD_MILLISECONDS = 3000 // a slower /health answer means the free host was asleep
const HEALTH_RETRY_MILLISECONDS = 5000

export default function App() {
  const [currentView, setCurrentView] = useState<View>('ask')
  const [theme, setTheme] = useState<Theme>(() => readSavedTheme() ?? readSystemTheme())
  const [hasChosenTheme, setHasChosenTheme] = useState(() => readSavedTheme() !== null)
  const [health, setHealth] = useState<HealthReport | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')
  const [investigations, setInvestigations] = useState<Investigation[]>([])
  const [openChunkId, setOpenChunkId] = useState<string | null>(null)
  const nextInvestigationId = useRef(1)

  const isInvestigating = investigations.some(isRunning)

  // Check the backend once on load, and keep retrying every few seconds until it answers "ok".
  useEffect(() => {
    let isMounted = true
    let retryTimer: number | undefined
    const checkHealth = async () => {
      const wakingTimer = window.setTimeout(() => isMounted && setConnectionState('waking'), WAKING_THRESHOLD_MILLISECONDS)
      try {
        const report = await fetchHealth()
        if (!isMounted) return
        setHealth(report)
        setConnectionState(report.status === 'ok' ? 'ready' : 'degraded')
        if (report.status !== 'ok') retryTimer = window.setTimeout(checkHealth, HEALTH_RETRY_MILLISECONDS)
      } catch {
        if (!isMounted) return
        setConnectionState('offline')
        retryTimer = window.setTimeout(checkHealth, HEALTH_RETRY_MILLISECONDS)
      } finally {
        window.clearTimeout(wakingTimer)
      }
    }
    checkHealth()
    return () => {
      isMounted = false
      window.clearTimeout(retryTimer)
    }
  }, [])

  // Follow the system theme until the visitor picks one with the toggle.
  useEffect(() => {
    if (hasChosenTheme) return
    const systemDarkQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const followSystem = () => setTheme(systemDarkQuery.matches ? 'dark' : 'light')
    systemDarkQuery.addEventListener('change', followSystem)
    return () => systemDarkQuery.removeEventListener('change', followSystem)
  }, [hasChosenTheme])

  const toggleTheme = () => {
    const nextTheme: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(nextTheme)
    setTheme(nextTheme)
    setHasChosenTheme(true)
  }

  // Replace one investigation in the list (by id) with an updated copy.
  const updateInvestigation = (id: number, update: (investigation: Investigation) => Investigation) => {
    setInvestigations((current) => current.map((investigation) => (investigation.id === id ? update(investigation) : investigation)))
  }

  const askQuestion = async (question: string) => {
    if (isInvestigating) return
    setCurrentView('ask')
    const id = nextInvestigationId.current++
    setInvestigations((current) => [...current, createInvestigation(id, question)])
    try {
      await streamInvestigation(question, (event) => updateInvestigation(id, (investigation) => applyInvestigationEvent(investigation, event)))
      // The stream can end without an answer or error event (e.g. the connection dropped).
      updateInvestigation(id, (investigation) =>
        isRunning(investigation) ? failInvestigation(investigation, 'The connection closed before the answer arrived.') : investigation)
    } catch (error) {
      updateInvestigation(id, (investigation) => failInvestigation(investigation, describeStreamError(error)))
    }
  }

  const closeSource = useCallback(() => setOpenChunkId(null), [])

  return (
    <div className="app">
      <Sidebar
        currentView={currentView}
        onChangeView={setCurrentView}
        onAskSampleQuestion={askQuestion}
        isInvestigating={isInvestigating}
        connectionState={connectionState}
        health={health}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      <main className="main">
        {currentView === 'ask' ? (
          <AskView
            investigations={investigations}
            isInvestigating={isInvestigating}
            onAsk={askQuestion}
            onRetry={askQuestion}
            onOpenSource={setOpenChunkId}
          />
        ) : (
          <DocumentsView />
        )}
      </main>
      {openChunkId && <SourceDrawer chunkId={openChunkId} onClose={closeSource} />}
    </div>
  )
}

function describeStreamError(error: unknown): string {
  if (error instanceof TypeError) {
    return 'Could not reach the server. Check the connection and try again.' // fetch throws TypeError when offline
  }
  return error instanceof Error ? error.message : 'Something went wrong while investigating.'
}
