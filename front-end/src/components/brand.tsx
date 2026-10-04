import { cn } from "@/lib/utils"

/**
 * The Gluco mark: a three-quarter ring, the same shape as the Gluco Score
 * gauge, so the logo, the assistant and the score read as one thing.
 */
export function GlucoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={cn("size-5 text-primary", className)}
    >
      <circle
        cx="12"
        cy="12"
        r="8.5"
        stroke="currentColor"
        strokeOpacity="0.22"
        strokeWidth="3.5"
      />
      <circle
        cx="12"
        cy="12"
        r="8.5"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray="72 100"
        transform="rotate(135 12 12)"
      />
    </svg>
  )
}

export function Brand({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 text-lg font-bold tracking-tight",
        className
      )}
    >
      <GlucoMark className="size-6" />
      gluco
    </span>
  )
}
