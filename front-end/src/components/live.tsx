"use client"

import { InfoIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { ClockState } from "@/lib/api/events"
import { formatClockTime, formatReplayTime } from "@/lib/format"
import { useLiveReadings } from "@/lib/live"
import { cn } from "@/lib/utils"

/** A small pulsing dot that marks a value as live. */
export function LiveDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("relative flex size-2 shrink-0", className)}
    >
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60 motion-reduce:animate-none" />
      <span className="relative inline-flex size-2 rounded-full bg-primary" />
    </span>
  )
}

/** The header strip in live mode: when the sensors and analytics last updated. */
export function LiveStatus({ clock }: { clock: ClockState }) {
  const live = useLiveReadings()
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <Badge variant="outline" className="gap-1.5 bg-background">
        <LiveDot />
        Live
      </Badge>
      <span className="flex items-center gap-1.5 whitespace-nowrap">
        <span className="text-muted-foreground">Sensors</span>
        <time
          dateTime={live.at ?? undefined}
          className="font-medium tabular-nums"
        >
          {formatClockTime(live.at)} UTC
        </time>
      </span>
      <span className="flex items-center gap-1.5 whitespace-nowrap">
        <span className="text-muted-foreground">Analytics as of</span>
        <time
          dateTime={clock.now ?? undefined}
          className="font-medium tabular-nums"
        >
          {formatReplayTime(clock.now)} UTC
        </time>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="text-muted-foreground"
              aria-label="About live data"
            >
              <InfoIcon className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-64">
            Heart rate, movement and skin temperature update every second. The
            Gluco Score and 24-hour averages update every 5 to 15 minutes.
          </TooltipContent>
        </Tooltip>
      </span>
    </div>
  )
}
