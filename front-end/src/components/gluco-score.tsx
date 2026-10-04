"use client"

import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon } from "lucide-react"

import { EstimateNote, type Audience } from "@/components/estimate-note"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { formatValue, GLUCO_CHANGE, GLUCO_SCORE } from "@/lib/catalog"

// Changes smaller than this many points read as "about the same".
const STEADY = 1

export function ChangeBadge({ change }: { change: number | null | undefined }) {
  if (change == null)
    return <Badge variant="outline">No 24 h comparison yet</Badge>
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
      {formatValue(GLUCO_CHANGE, change, { signed: true })} pts vs 24 h ago
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

/** The headline Gluco Score: value out of 100, its 24 h change, and the estimate note. */
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
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-2">
        <span className="text-5xl font-semibold tracking-tight tabular-nums">
          {formatValue(GLUCO_SCORE, value)}
        </span>
        <span className="pb-1.5 text-muted-foreground">/ 100</span>
      </div>
      <Progress value={value ?? 0} aria-label="Gluco Score out of 100" />
      {audience === "patient" ? (
        <p className="text-sm">
          {friendlyChange(change)}{" "}
          <span className="text-muted-foreground">Higher is healthier.</span>
        </p>
      ) : (
        <div>
          <ChangeBadge change={change} />
        </div>
      )}
      <EstimateNote audience={audience} />
    </div>
  )
}
