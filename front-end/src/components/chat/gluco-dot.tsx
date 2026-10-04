"use client"

import { cn } from "@/lib/utils"

export type GlucoMood = "idle" | "open" | "thinking" | "happy"

/** Soft round face for the Gluco assistant. Sized by the parent via size-*. */
export function GlucoDot({
  mood = "idle",
  className,
}: {
  mood?: GlucoMood
  className?: string
}) {
  return (
    <span
      data-mood={mood}
      aria-hidden="true"
      className={cn(
        "gluco-dot relative inline-flex shrink-0 rounded-full text-primary-foreground",
        className
      )}
    >
      <span className="absolute inset-0 flex items-center justify-center gap-[16cqw] pb-[10cqw]">
        <span className="gluco-eye flex items-end justify-center">
          <span className="gluco-pupil" />
        </span>
        <span className="gluco-eye flex items-end justify-center">
          <span className="gluco-pupil" />
        </span>
      </span>
    </span>
  )
}

/** Three bouncing dots shown while Gluco is composing an answer. */
export function ThinkingDots({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("thinking-dots inline-flex items-end gap-0.5", className)}
    >
      <span />
      <span />
      <span />
    </span>
  )
}
