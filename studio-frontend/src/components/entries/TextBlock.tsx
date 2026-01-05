interface Props {
  content: string
}

export function TextBlock({ content }: Props) {
  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 rounded-full bg-bg-tertiary flex items-center justify-center">
        <span className="text-text-muted text-sm">A</span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-text-muted mb-1">Assistant</div>
        <div className="text-text-primary whitespace-pre-wrap break-words">
          {content}
        </div>
      </div>
    </div>
  )
}
