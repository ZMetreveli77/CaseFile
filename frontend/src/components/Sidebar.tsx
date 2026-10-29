import type { HealthReport } from '../types'
import type { Theme } from '../theme'
import { SAMPLE_QUESTIONS } from '../sampleQuestions'
import { Icon } from './Icon'
import { StatusIndicator, type ConnectionState } from './StatusIndicator'

export type View = 'ask' | 'documents'

const COPYRIGHT_YEAR = 2026 // the year CaseFile was written, as in LICENSE

interface SidebarProps {
  currentView: View
  onChangeView: (view: View) => void
  onAskSampleQuestion: (question: string) => void
  isInvestigating: boolean
  connectionState: ConnectionState
  health: HealthReport | null
  theme: Theme
  onToggleTheme: () => void
}

export function Sidebar(props: SidebarProps) {
  const nextTheme = props.theme === 'dark' ? 'light' : 'dark'
  return (
    <aside className={`sidebar sidebar--${props.currentView}`}>
      <div className="sidebar-head">
        <span className="brand">CaseFile</span>
        <button
          type="button"
          className="icon-button"
          onClick={props.onToggleTheme}
          aria-label={`Switch to ${nextTheme} theme`}
          title={`Switch to ${nextTheme} theme`}
        >
          <Icon name={props.theme === 'dark' ? 'sun' : 'moon'} />
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        <button
          type="button"
          className="nav-item"
          aria-current={props.currentView === 'ask' ? 'page' : undefined}
          onClick={() => props.onChangeView('ask')}
        >
          <Icon name="ask" /> Ask
        </button>
        <button
          type="button"
          className="nav-item"
          aria-current={props.currentView === 'documents' ? 'page' : undefined}
          onClick={() => props.onChangeView('documents')}
        >
          <Icon name="document" /> Documents
        </button>
      </nav>

      <section className="samples" aria-labelledby="samples-heading">
        <h2 id="samples-heading" className="sidebar-heading">Try a question</h2>
        <div className="sample-list">
          {SAMPLE_QUESTIONS.map((sample) => (
            <button
              key={sample.question}
              type="button"
              className="sample"
              disabled={props.isInvestigating}
              onClick={() => props.onAskSampleQuestion(sample.question)}
            >
              <span className="sample-question">{sample.question}</span>
              <span className="sample-outcome">{sample.outcome}</span>
            </button>
          ))}
        </div>
      </section>

      <StatusIndicator connectionState={props.connectionState} health={props.health} />
      <p className="copyright">© {COPYRIGHT_YEAR} Zuka Metreveli</p>
    </aside>
  )
}
