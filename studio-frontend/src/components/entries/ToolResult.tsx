import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'

interface Props {
  content: string
}

export function ToolResult({ content }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const isLong = content.length > 300
  const preview = content.slice(0, 300)

  return (
    <div className="flex gap-3 ml-10">
      <div className="shrink-0 w-5 h-5 rounded bg-bg-tertiary flex items-center justify-center">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-text-muted">
          <polyline points="4,17 10,11 4,5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <button
          onClick={() => isLong && setIsExpanded(!isExpanded)}
          className={clsx(
            'text-xs text-text-muted mb-1 flex items-center gap-1',
            isLong && 'hover:text-text-secondary cursor-pointer'
          )}
        >
          {isLong && (
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={clsx('transition-transform', isExpanded && 'rotate-90')}
            >
              <polyline points="9,18 15,12 9,6" />
            </svg>
          )}
          Output
        </button>
        <div className="bg-bg-primary border border-border-subtle rounded px-3 py-2">
          <AnimatePresence mode="wait">
            <motion.pre
              key={isExpanded ? 'full' : 'preview'}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.1 }}
              className="text-xs font-mono text-text-secondary whitespace-pre-wrap break-words overflow-x-auto"
            >
              {isExpanded || !isLong ? content : preview}
              {!isExpanded && isLong && (
                <span className="text-text-muted">... ({content.length - 300} more chars)</span>
              )}
            </motion.pre>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
