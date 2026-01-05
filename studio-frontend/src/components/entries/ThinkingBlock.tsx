import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'

interface Props {
  content: string
}

export function ThinkingBlock({ content }: Props) {
  const [isExpanded, setIsExpanded] = useState(false)
  const preview = content.slice(0, 120)
  const hasMore = content.length > 120

  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 rounded-full bg-bg-tertiary flex items-center justify-center">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-text-muted">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-text-muted mb-1 flex items-center gap-1 hover:text-text-secondary transition-colors"
        >
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
          Thinking
        </button>
        <div className="bg-bg-tertiary/50 rounded-lg px-3 py-2 border border-border-subtle">
          <AnimatePresence mode="wait">
            <motion.div
              key={isExpanded ? 'full' : 'preview'}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="text-sm text-text-secondary whitespace-pre-wrap break-words"
            >
              {isExpanded ? content : preview}
              {!isExpanded && hasMore && (
                <span className="text-text-muted">...</span>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
