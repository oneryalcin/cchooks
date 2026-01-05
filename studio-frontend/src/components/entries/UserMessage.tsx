interface Props {
  content: string
}

export function UserMessage({ content }: Props) {
  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 rounded-full bg-highlight/20 flex items-center justify-center">
        <span className="text-highlight text-sm">U</span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-text-muted mb-1">User</div>
        <div className="text-text-primary whitespace-pre-wrap break-words">
          {content}
        </div>
      </div>
    </div>
  )
}
