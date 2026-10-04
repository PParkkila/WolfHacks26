"use client"

import { InfoIcon, PauseIcon, PlayIcon } from "lucide-react"
import { useState } from "react"

import { LiveStatus } from "@/components/live"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useClock } from "@/lib/clock"
import { formatReplayTime } from "@/lib/format"

const HOUR_MS = 3_600_000
// Real seconds per simulated hour.
const SPEEDS = [1, 2, 5, 15]

export function AsOf() {
  const { clock } = useClock()
  if (!clock?.now) return <Skeleton className="h-4 w-44" />
  return (
    <span className="flex items-center gap-1.5 text-sm whitespace-nowrap">
      <span className="text-muted-foreground">Data as of</span>
      <time dateTime={clock.now} className="font-medium tabular-nums">
        {formatReplayTime(clock.now)} UTC
      </time>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="text-muted-foreground"
            aria-label="About the demo time"
          >
            <InfoIcon className="size-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          This demo moves through a week of data as if it were happening now.
          Changing the time changes everyone&apos;s view.
        </TooltipContent>
      </Tooltip>
    </span>
  )
}

export function ReplayControls() {
  const { clock, control } = useClock()
  const [dragging, setDragging] = useState<number | null>(null)

  if (!clock?.now || !clock.data_start || !clock.data_end) {
    return <Skeleton className="h-8 w-full" />
  }
  // Replay off: the data is live, so there is no demo time to control.
  if (!clock.enabled) return <LiveStatus clock={clock} />

  const start = Date.parse(clock.data_start)
  const end = Date.parse(clock.data_end)
  const now = Date.parse(clock.now)
  const shown = dragging ?? now

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-3">
        <Badge variant="outline" className="bg-background">
          Demo time
        </Badge>
        <Button
          size="icon-sm"
          variant="outline"
          disabled={!clock.enabled || (clock.at_end && !clock.playing)}
          onClick={() => control({ action: clock.playing ? "pause" : "play" })}
          aria-label={clock.playing ? "Pause demo" : "Play demo"}
        >
          {clock.playing ? <PauseIcon /> : <PlayIcon />}
        </Button>
        <AsOf />
        {clock.at_end ? (
          <Badge variant="secondary">End of demo data</Badge>
        ) : null}
      </div>

      <div className="flex min-w-48 flex-1 items-center gap-3">
        <Slider
          aria-label="Demo time position"
          min={start}
          max={end}
          step={HOUR_MS}
          value={[Math.min(Math.max(shown, start), end)]}
          disabled={!clock.enabled}
          onValueChange={([value]) => setDragging(value)}
          onValueCommit={([value]) => {
            void control({ action: "seek", to: new Date(value).toISOString() })
            // For keyboard input Radix commits before it reports the change, so
            // clear the drag state after that change has landed.
            setTimeout(() => setDragging(null), 0)
          }}
        />
        {dragging !== null ? (
          <span className="w-32 shrink-0 text-xs text-muted-foreground tabular-nums">
            {formatReplayTime(new Date(dragging).toISOString())}
          </span>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">
          1 hour of data every
        </span>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          value={String(clock.seconds_per_hour)}
          onValueChange={(value) => {
            if (value)
              void control({
                action: "speed",
                seconds_per_hour: Number(value),
              })
          }}
          aria-label="Demo speed"
        >
          {SPEEDS.map((seconds) => (
            <ToggleGroupItem key={seconds} value={String(seconds)}>
              {seconds}s
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
    </div>
  )
}
