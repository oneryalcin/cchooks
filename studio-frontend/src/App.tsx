import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { SessionList } from './components/SessionList'
import { ConversationView } from './components/ConversationView'

export default function App() {
  const [selectedSession, setSelectedSession] = useState<string | null>(null)
  const { isConnected } = useWebSocket()

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <aside className="w-72 border-r border-border flex flex-col bg-bg-secondary">
        {/* Logo/Title */}
        <header className="px-4 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-accent/20 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>
            <div>
              <h1 className="text-base font-semibold text-text-primary">FastHooks</h1>
              <p className="text-xs text-text-muted">Studio</p>
            </div>
          </div>
        </header>

        {/* Sessions */}
        <div className="flex-1 overflow-y-auto">
          <SessionList
            selectedSession={selectedSession}
            onSelectSession={setSelectedSession}
          />
        </div>

        {/* Status footer */}
        <footer className="px-4 py-3 border-t border-border text-xs">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-allow' : 'bg-deny'}`} />
            <span className="text-text-muted">
              {isConnected ? 'Live' : 'Disconnected'}
            </span>
          </div>
        </footer>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden flex flex-col bg-bg-primary">
        {selectedSession ? (
          <ConversationView sessionId={selectedSession} />
        ) : (
          <EmptyState />
        )}
      </main>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-bg-tertiary flex items-center justify-center">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-text-muted">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
        </div>
        <h2 className="text-lg font-medium text-text-primary mb-1">No session selected</h2>
        <p className="text-sm text-text-muted">Select a session from the sidebar to view hook events</p>
      </div>
    </div>
  )
}
