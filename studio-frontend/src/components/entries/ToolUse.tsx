import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'
import type { HookData } from '../../lib/api'
import { HookEvents } from '../HookEvents'

interface Props {
  name: string
  input: Record<string, unknown>
  hooks?: HookData
}

export function ToolUse({ name, input, hooks }: Props) {
  const [showInput, setShowInput] = useState(false)

  // Get a preview of the input
  const inputPreview = getInputPreview(name, input)

  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent">
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-text-muted mb-1">Tool</div>

        {/* Tool call header */}
        <div className="bg-bg-secondary rounded-lg border border-border overflow-hidden">
          <div className="px-3 py-2 flex items-center gap-2 bg-bg-tertiary/30">
            <span className="font-mono text-sm font-medium text-accent">{name}</span>
            {inputPreview && (
              <span className="text-sm text-text-secondary truncate">
                {inputPreview}
              </span>
            )}
          </div>

          {/* Hook events - THE KEY FEATURE */}
          {hooks && (
            <div className="border-t border-border">
              <HookEvents hooks={hooks} />
            </div>
          )}

          {/* Input toggle */}
          <div className="border-t border-border-subtle">
            <button
              onClick={() => setShowInput(!showInput)}
              className="w-full px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary hover:bg-bg-tertiary/30 transition-colors flex items-center gap-1"
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className={clsx('transition-transform', showInput && 'rotate-90')}
              >
                <polyline points="9,18 15,12 9,6" />
              </svg>
              Input
            </button>
            <AnimatePresence>
              {showInput && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="overflow-hidden"
                >
                  <pre className="px-3 py-2 text-xs font-mono text-text-secondary bg-bg-primary/50 overflow-x-auto">
                    {JSON.stringify(input, null, 2)}
                  </pre>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  )
}

function getInputPreview(name: string, input: Record<string, unknown>): string {
  // Tool-specific previews
  if (name === 'Bash' && typeof input.command === 'string') {
    return truncate(input.command, 60)
  }
  if ((name === 'Write' || name === 'Read') && typeof input.file_path === 'string') {
    return truncate(input.file_path, 60)
  }
  if (name === 'Edit' && typeof input.file_path === 'string') {
    return truncate(input.file_path, 60)
  }
  if (name === 'Grep' && typeof input.pattern === 'string') {
    return truncate(input.pattern, 60)
  }
  if (name === 'Glob' && typeof input.pattern === 'string') {
    return truncate(input.pattern, 60)
  }
  return ''
}

function truncate(str: string, len: number): string {
  if (str.length <= len) return str
  return str.slice(0, len) + '...'
}
