import { useSessions } from '../hooks/useSessions'
import { motion } from 'framer-motion'
import clsx from 'clsx'

interface Props {
  selectedSession: string | null
  onSelectSession: (id: string) => void
}

export function SessionList({ selectedSession, onSelectSession }: Props) {
  const { data: sessions, isLoading, error } = useSessions()

  if (isLoading) {
    return (
      <div className="p-4">
        <div className="animate-pulse space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-bg-tertiary rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-deny text-sm">
        Failed to load sessions
      </div>
    )
  }

  if (!sessions?.length) {
    return (
      <div className="p-4 text-text-muted text-sm">
        No sessions yet. Run a hook with SQLiteObserver to see events here.
      </div>
    )
  }

  return (
    <div className="p-2 space-y-1">
      <div className="px-2 py-1 text-xs font-medium text-text-muted uppercase tracking-wider">
        Sessions ({sessions.length})
      </div>
      {sessions.map((session, index) => (
        <motion.button
          key={session.session_id}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: index * 0.03 }}
          onClick={() => onSelectSession(session.session_id)}
          className={clsx(
            'w-full text-left px-3 py-2.5 rounded-lg transition-colors',
            selectedSession === session.session_id
              ? 'bg-accent/10 border border-accent/30'
              : 'hover:bg-bg-tertiary border border-transparent'
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="font-mono text-sm text-text-primary truncate">
                {session.session_id.slice(0, 8)}...
              </div>
              <div className="text-xs text-text-muted mt-0.5">
                {formatRelativeTime(session.last_seen)}
              </div>
            </div>
            <div className="flex flex-col items-end gap-0.5 text-xs shrink-0">
              <span className="px-1.5 py-0.5 bg-bg-elevated rounded text-text-secondary">
                {session.hook_count} hooks
              </span>
              <span className="text-text-muted">
                {session.event_count} events
              </span>
            </div>
          </div>
        </motion.button>
      ))}
    </div>
  )
}

function formatRelativeTime(unixTimestamp: number): string {
  const date = new Date(unixTimestamp * 1000) // Convert seconds to ms
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}
