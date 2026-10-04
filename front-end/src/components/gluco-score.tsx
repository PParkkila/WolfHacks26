"use client"

import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon } from "lucide-react"

import { EstimateNote, type Audience } from "@/components/estimate-note"
import { Badge } from "@/components/ui/badge"
import { formatValue, GLUCO_CHANGE, GLUCO_SCORE } from "@/lib/catalog"
import { cn } from "@/lib/utils"

// Changes smaller than this many points read as "about the same".
const STEADY = 1

export function ChangeBadge({ change }: { change: number | null | undefined }) {
  if (change == null)
    return <Badge variant="outline">No 24 h comparison available</Badge>
  const Icon =
    change >= STEADY
      ? ArrowUpRightIcon
      : change <= -STEADY
        ? ArrowDownRightIcon
        : MinusIcon
  return (
    <Badge
      variant={
        change <= -10
          ? "destructive"
          : change >= STEADY
            ? "secondary"
            : "outline"
      }
    >
      <Icon data-icon="inline-start" />
      {formatValue(GLUCO_CHANGE, change, { signed: true })} pts vs 24 h prior
    </Badge>
  )
}

/** "Up 3 points since this time yesterday." */
export function friendlyChange(change: number | null | undefined): string {
  if (change == null)
    return "We need a full day of readings before we can compare."
  const points = Math.round(Math.abs(change))
  const unit = points === 1 ? "point" : "points"
  if (change >= STEADY) return `Up ${points} ${unit} since this time yesterday.`
  if (change <= -STEADY)
    return `Down ${points} ${unit} since this time yesterday.`
  return "About the same as this time yesterday."
}

// The ring covers 270 degrees (75 of 100 path units), open at the bottom,
// matching the Gluco mark.
const ARC = 75

/**
 * The Gluco Score as a ring meter: one hue, filled in proportion to the score,
 * on a lighter step of the same ramp. There are no coloured bands, because the
 * model doesn't define clinical thresholds.
 */
export function ScoreRing({
  value,
  className,
}: {
  value: number | null | undefined
  className?: string
}) {
  const score = value == null ? null : Math.min(Math.max(value, 0), 100)
  const filled = score == null ? 0 : (ARC * score) / 100
  return (
    <div
      role="meter"
      aria-label="Gluco Score"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score ?? undefined}
      aria-valuetext={
        score == null ? "No score yet" : `${Math.round(score)} out of 100`
      }
      className={cn("relative size-36 shrink-0", className)}
    >
      <svg viewBox="0 0 120 120" fill="none" className="size-full">
        <g transform="rotate(135 60 60)" strokeWidth="10" strokeLinecap="round">
          <circle
            cx="60"
            cy="60"
            r="52"
            pathLength="100"
            strokeDasharray={`${ARC} 100`}
            className="stroke-brand-track"
          />
          {filled > 0 ? (
            <circle
              cx="60"
              cy="60"
              r="52"
              pathLength="100"
              strokeDasharray={`${filled} 100`}
              className="stroke-primary transition-[stroke-dasharray] duration-700 ease-out motion-reduce:transition-none"
            />
          ) : null}
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pt-1">
        <span className="text-4xl leading-none font-bold tracking-tight">
          {formatValue(GLUCO_SCORE, value)}
        </span>
        <span className="mt-1 text-xs text-muted-foreground">of 100</span>
      </div>
    </div>
  )
}

/** The headline Gluco Score: the ring, its 24 h change, and the estimate note. */
export function GlucoScore({
  value,
  change,
  audience,
}: {
  value: number | null | undefined
  change: number | null | undefined
  audience: Audience
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <ScoreRing value={value} />
        {audience === "patient" ? (
          <div className="flex max-w-56 min-w-36 flex-1 flex-col gap-1">
            <p className="text-base font-medium text-pretty">
              {friendlyChange(change)}
            </p>
            <p className="text-sm text-muted-foreground">Higher is healthier.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <ChangeBadge change={change} />
            <p className="text-sm text-muted-foreground">Higher is healthier.</p>
          </div>
        )}
      </div>
      <EstimateNote audience={audience} />
    </div>
  )
}
