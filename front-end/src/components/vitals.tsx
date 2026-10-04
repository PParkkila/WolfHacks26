"use client"

import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  FootprintsIcon,
  HeartPulseIcon,
  InfoIcon,
  MinusIcon,
  ThermometerIcon,
  type LucideIcon,
} from "lucide-react"
import { Area, AreaChart, ReferenceLine, XAxis, YAxis } from "recharts"

import { LiveDot } from "@/components/live"
import { Card } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card"
import type { Schemas } from "@/lib/api/client"
import type { QueryResult } from "@/lib/api/events"
import {
  formatValue,
  roundValue,
  shortUnit,
  type MetricInfo,
} from "@/lib/catalog"
import { formatReplayDay } from "@/lib/format"
import { cn } from "@/lib/utils"

type MetricChange = Schemas["MetricChange"]

/**
 * The three readings a patient leads with, in plain words: each 24-hour
 * average and the live reading of the same sensor.
 */
export const PRIMARY_VITALS: {
  metric: string
  liveMetric: string
  title: string
  icon: LucideIcon
}[] = [
  {
    metric: "hr_mean_bpm_24h",
    liveMetric: "latest_hr_bpm",
    title: "Heart rate",
    icon: HeartPulseIcon,
  },
  {
    metric: "motion_mean_g",
    liveMetric: "latest_motion_g",
    title: "Movement",
    icon: FootprintsIcon,
  },
  {
    metric: "temperature_mean_c_24h",
    liveMetric: "latest_skin_temperature_c",
    title: "Skin temperature",
    icon: ThermometerIcon,
  },
]

type Tone = "usual" | "good" | "watch" | "notable" | "unknown"

type Status = { tone: Tone; label: string; icon: LucideIcon }

/**
 * How today compares with this person's own usual week, from the z-score
 * against their 7-day baseline. A shift in a metric's healthy direction reads
 * as good; any other large shift as "worth a look", never as a diagnosis.
 */
export function usualStatus(
  z: number | null | undefined,
  higherIsBetter: boolean | null | undefined
): Status {
  if (z == null)
    return {
      tone: "unknown",
      label: "Not enough readings yet",
      icon: MinusIcon,
    }
  const size = Math.abs(z)
  if (size < 1)
    return { tone: "usual", label: "Close to your usual", icon: CheckIcon }
  const label = `${size >= 2 ? "A lot" : "A bit"} ${z > 0 ? "higher" : "lower"} than usual`
  const icon = z > 0 ? ArrowUpIcon : ArrowDownIcon
  const good = higherIsBetter != null && z > 0 === higherIsBetter
  return { tone: good ? "good" : size >= 2 ? "notable" : "watch", label, icon }
}

const TONE_CHIP: Record<Tone, string> = {
  usual: "bg-accent text-accent-foreground [&>svg]:text-primary",
  good: "bg-accent text-accent-foreground [&>svg]:text-primary",
  watch: "bg-watch/15 text-foreground [&>svg]:text-watch",
  notable: "bg-notable/15 text-foreground [&>svg]:text-notable",
  unknown: "bg-muted text-muted-foreground",
}

const TONE_FILL: Record<Tone, string> = {
  usual: "bg-primary",
  good: "bg-primary",
  watch: "bg-watch",
  notable: "bg-notable",
  unknown: "bg-muted-foreground",
}

export function StatusChip({
  status,
  className,
}: {
  status: Status
  className?: string
}) {
  const Icon = status.icon
  return (
    <span
      className={cn(
        "inline-flex h-6 w-fit shrink-0 items-center gap-1 rounded-full px-2.5 text-xs font-medium whitespace-nowrap [&>svg]:size-3.5",
        TONE_CHIP[status.tone],
        className
      )}
    >
      <Icon aria-hidden="true" />
      {status.label}
    </span>
  )
}

/**
 * Where today sits against this person's usual range: the middle band is
 * within one standard deviation of their own week, the ends are two or more.
 */
export function UsualGauge({
  z,
  status,
}: {
  z: number | null | undefined
  status: Status
}) {
  const position =
    z == null ? null : ((Math.min(Math.max(z, -3), 3) + 3) / 6) * 100
  return (
    <div className="flex flex-col gap-1.5" aria-hidden="true">
      <div className="relative h-1.5 rounded-full bg-foreground/10">
        <div className="absolute inset-y-0 left-1/3 w-1/3 rounded-full bg-primary/35" />
        {position == null ? null : (
          <span
            className={cn(
              "absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card transition-[left] duration-500 ease-out motion-reduce:transition-none",
              TONE_FILL[status.tone]
            )}
            style={{ left: `${position}%` }}
          />
        )}
      </div>
      <div className="grid grid-cols-3 text-[11px] text-muted-foreground">
        <span>Lower</span>
        <span className="text-center">Usual</span>
        <span className="text-right">Higher</span>
      </div>
    </div>
  )
}

function MetricInfoButton({ info }: { info: MetricInfo | undefined }) {
  if (!info) return null
  return (
    <HoverCard openDelay={150}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          aria-label={`About ${info.label}`}
          className="text-muted-foreground hover:text-foreground"
        >
          <InfoIcon className="size-3.5" />
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="text-sm">
        {info.description}
      </HoverCardContent>
    </HoverCard>
  )
}

/** A live reading on one line: pulsing dot, label, value. */
export function LiveValue({
  metric,
  info,
  value,
  label = "Right now",
}: {
  metric: string
  info: MetricInfo | undefined
  value: number | null | undefined
  label?: string
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-accent/60 px-3 py-2">
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <LiveDot />
        {label}
      </span>
      {value == null ? (
        <span className="text-sm text-muted-foreground">No reading</span>
      ) : (
        <Value metric={metric} info={info} value={value} size="sm" />
      )}
    </div>
  )
}

function Value({
  metric,
  info,
  value,
  size,
}: {
  metric: string
  info: MetricInfo | undefined
  value: number | null | undefined
  size: "lg" | "sm"
}) {
  const unit = value == null ? "" : shortUnit(info?.unit)
  return (
    <span className="flex items-baseline gap-1">
      <span
        className={cn(
          "font-bold tracking-tight",
          size === "lg" ? "text-4xl" : "text-xl"
        )}
      >
        {formatValue(metric, value)}
      </span>
      {unit ? (
        <span className="text-sm font-medium text-muted-foreground">
          {unit}
        </span>
      ) : null}
    </span>
  )
}

/** Daily means for one metric from a multi-metric /query result. */
function dailyPoints(week: QueryResult | undefined, metric: string) {
  const points = week?.series[0]?.points ?? []
  return points.flatMap((point) => {
    const value = point[metric]
    return typeof value === "number" && Number.isFinite(value)
      ? [{ t: String(point.t), v: roundValue(metric, value) }]
      : []
  })
}

/** Seven daily means with the person's usual level as a dashed line. */
function Sparkline({
  metric,
  info,
  week,
  baseline,
}: {
  metric: string
  info: MetricInfo | undefined
  week: QueryResult | undefined
  baseline: number | null | undefined
}) {
  const rows = dailyPoints(week, metric)
  if (rows.length < 2)
    return (
      <div className="flex h-16 items-center text-xs text-muted-foreground">
        A week of readings will show here.
      </div>
    )
  const values = rows.map((r) => r.v)
  if (baseline != null) values.push(baseline)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const pad = (max - min) * 0.2 || Math.abs(max) * 0.05 || 1
  const config: ChartConfig = {
    v: { label: info?.label ?? metric, color: "var(--primary)" },
  }
  const gradient = `spark-${metric}`
  return (
    <ChartContainer config={config} className="aspect-auto h-16 w-full">
      <AreaChart data={rows} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-v)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--color-v)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="t" hide />
        <YAxis hide domain={[min - pad, max + pad]} />
        {baseline != null ? (
          <ReferenceLine
            y={baseline}
            stroke="var(--muted-foreground)"
            strokeDasharray="3 3"
            strokeOpacity={0.6}
          />
        ) : null}
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) =>
                formatReplayDay(payload?.[0]?.payload?.t)
              }
            />
          }
        />
        <Area
          dataKey="v"
          type="monotone"
          stroke="var(--color-v)"
          strokeWidth={2}
          fill={`url(#${gradient})`}
          dot={false}
          activeDot={{ r: 4 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ChartContainer>
  )
}

/** A headline vital: value, how it compares with usual, and its week. */
export function VitalTile({
  title,
  icon: Icon,
  metric,
  info,
  value,
  change,
  week,
  live,
}: {
  title: string
  icon: LucideIcon
  metric: string
  info: MetricInfo | undefined
  value: number | null | undefined
  change: MetricChange | undefined
  week: QueryResult | undefined
  /** The live reading of this sensor, when the data is live. */
  live?: { metric: string; info: MetricInfo | undefined; value: number | null }
}) {
  const status = usualStatus(change?.z_vs_baseline, info?.higher_is_better)
  return (
    <Card className="gap-4 px-5">
      <div className="flex items-center gap-2.5">
        <span className="flex size-8 items-center justify-center rounded-full bg-accent text-primary">
          <Icon className="size-4" />
        </span>
        <span className="font-semibold">{title}</span>
        <span className="ml-auto">
          <MetricInfoButton info={info} />
        </span>
      </div>
      {live ? <LiveValue {...live} /> : null}
      <div className="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
        <div className="flex flex-col gap-0.5">
          <Value metric={metric} info={info} value={value} size="lg" />
          {live ? (
            <span className="text-xs text-muted-foreground">
              24-hour average
            </span>
          ) : null}
        </div>
        <StatusChip status={status} />
      </div>
      <div className="flex flex-col gap-1">
        <Sparkline
          metric={metric}
          info={info}
          week={week}
          baseline={change?.baseline_mean}
        />
        <p className="text-xs text-muted-foreground">
          Last 7 days
          {change?.baseline_mean != null ? (
            <>
              . Dashed line: your usual,{" "}
              {formatValue(metric, change.baseline_mean)}
              {shortUnit(info?.unit) ? ` ${shortUnit(info?.unit)}` : ""}.
            </>
          ) : null}
        </p>
      </div>
    </Card>
  )
}

/** A secondary reading: compact value plus the usual-range gauge. */
export function ReadingRow({
  metric,
  info,
  value,
  change,
}: {
  metric: string
  info: MetricInfo | undefined
  value: number | null | undefined
  change: MetricChange | undefined
}) {
  const status = usualStatus(change?.z_vs_baseline, info?.higher_is_better)
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-muted/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            {info?.label ?? metric}
            <MetricInfoButton info={info} />
          </span>
          <Value metric={metric} info={info} value={value} size="sm" />
        </div>
        <StatusChip status={status} className="mt-0.5" />
      </div>
      <UsualGauge z={change?.z_vs_baseline} status={status} />
    </div>
  )
}
