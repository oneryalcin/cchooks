import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'
import type { HookData } from '../lib/api'

interface Props {
  hooks: HookData
}

export function HookEvents({ hooks }: Props) {
  const [showDetails, setShowDetails] = useState(true)

  // Determine overall status
  const hasDeny = hooks.handlers.some(h => h.decision === 'deny' || h.decision === 'block')
  const hasError = hooks.handlers.some(h => h.decision === 'error')

  return (
    <div className="bg-bg-primary/30">
      {/* Header */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="w-full px-3 py-2 flex items-center justify-between hover:bg-bg-tertiary/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className={clsx(
              'text-text-muted transition-transform',
              showDetails && 'rotate-90'
            )}
          >
            <polyline points="9,18 15,12 9,6" />
          </svg>
          <span className="text-xs font-medium text-accent">
            {hooks.hook_event_name}
          </span>
          <span className="text-xs text-text-muted">
            {hooks.handlers.length} handler{hooks.handlers.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {hasDeny && (
            <span className="px-1.5 py-0.5 text-xs rounded bg-deny/20 text-deny font-medium">
              DENIED
            </span>
          )}
          {hasError && (
            <span className="px-1.5 py-0.5 text-xs rounded bg-deny/20 text-deny font-medium">
              ERROR
            </span>
          )}
          <span className="text-xs font-mono text-text-muted">
            {hooks.total_duration_ms.toFixed(1)}ms
          </span>
        </div>
      </button>

      {/* Handler list */}
      <AnimatePresence>
        {showDetails && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-2 space-y-1">
              {hooks.handlers.map((handler, i) => (
                <HandlerRow key={i} handler={handler} index={i} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function HandlerRow({ handler, index }: { handler: HookData['handlers'][0]; index: number }) {
  const decision = handler.decision || 'allow'
  const decisionConfig = getDecisionConfig(decision)

  return (
    <motion.div
      initial={{ opacity: 0, x: -5 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.03 }}
      className="flex items-center gap-2 text-xs"
    >
      {/* Handler name */}
      <span className="font-mono text-text-secondary min-w-0 truncate">
        {handler.name}
      </span>

      {/* Arrow */}
      <span className="text-text-muted shrink-0">→</span>

      {/* Decision badge */}
      <span
        className={clsx(
          'shrink-0 px-1.5 py-0.5 rounded font-medium flex items-center gap-1',
          decisionConfig.bg,
          decisionConfig.text
        )}
      >
        <span>{decisionConfig.icon}</span>
        <span>{decision}</span>
      </span>

      {/* Duration */}
      {handler.duration_ms !== null && (
        <span className="font-mono text-text-muted shrink-0">
          {handler.duration_ms.toFixed(2)}ms
        </span>
      )}

      {/* Reason (if denied/blocked) */}
      {handler.reason && (
        <span className="text-text-muted italic truncate min-w-0">
          "{handler.reason}"
        </span>
      )}
    </motion.div>
  )
}

function getDecisionConfig(decision: string) {
  switch (decision) {
    case 'allow':
      return { icon: '✓', bg: 'bg-allow/20', text: 'text-allow' }
    case 'deny':
      return { icon: '✕', bg: 'bg-deny/20', text: 'text-deny' }
    case 'block':
      return { icon: '⊘', bg: 'bg-block/20', text: 'text-block' }
    case 'skip':
      return { icon: '⏭', bg: 'bg-skip/20', text: 'text-skip' }
    case 'error':
      return { icon: '!', bg: 'bg-deny/20', text: 'text-deny' }
    default:
      return { icon: '?', bg: 'bg-bg-tertiary', text: 'text-text-muted' }
  }
}
