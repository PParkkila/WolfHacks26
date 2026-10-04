"use client"

import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon } from "lucide-react"

import type { Audience } from "@/components/estimate-note"
import { ScoreRing } from "@/components/gluco-score"
import { QueryChart } from "@/components/query-chart"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { QueryResult, WidgetSpec } from "@/lib/api/events"
import {
  formatValue,
  formatWithUnit,
  GLUCO_SCORE,
  shortUnit,
  useMetrics,
} from "@/lib/catalog"
import { cn } from "@/lib/utils"

type Series = QueryResult["series"][number]
type Kind = WidgetSpec["kind"]

function numberAt(point: Record<string, unknown>, metric: string) {
  const value = point[metric]
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/** A series' values for one metric, oldest first, skipping gaps. */
function valuesOf(series: Series, metric: string) {
  return series.points.flatMap((point) => {
    const value = numberAt(point, metric)
    return value === null ? [] : [{ t: String(point.t), value }]
  })
}

function lastValue(series: Series, metric: string) {
  return valuesOf(series, metric).at(-1)?.value ?? null
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * 100).toFixed(1)},${(
          30 -
          ((v - min) / span) * 26 -
          2
        ).toFixed(1)}`
    )
    .join(" ")
  return (
    <svg
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      aria-hidden
      className="h-10 w-full overflow-visible"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

/** One headline number, how it moved over the range, and a sparkline. */
function StatWidget({ result }: { result: QueryResult }) {
  const metrics = useMetrics()
  const metric = result.metrics[0]
  const info = metrics.get(metric)
  const series = result.series[0]
  const values = series ? valuesOf(series, metric) : []
  if (!values.length) return <Empty />

  const latest = values.at(-1)!.value
  const delta = latest - values[0].value
  const flat = Math.abs(delta) < 1e-9
  const better =
    flat || info?.higher_is_better == null
      ? null
      : delta > 0 === info.higher_is_better
  const Arrow = flat
    ? MinusIcon
    : delta > 0
      ? ArrowUpRightIcon
      : ArrowDownRightIcon

  return (
    <div className="flex items-center gap-4">
      {metric === GLUCO_SCORE ? (
        <ScoreRing value={latest} className="size-32" />
      ) : (
        <div className="flex shrink-0 flex-col">
          <span className="text-4xl leading-none font-bold tracking-tight">
            {formatValue(metric, latest)}
          </span>
          <span className="mt-1 text-xs text-muted-foreground">
            {shortUnit(info?.unit)}
          </span>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate text-xs text-muted-foreground">
          {series.display_name} · {info?.label ?? metric}
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-1 text-sm font-medium",
            better === true && "text-primary",
            better === false && "text-destructive",
            better === null && "text-muted-foreground"
          )}
        >
          <Arrow aria-hidden className="size-4" />
          {formatValue(metric, delta, { signed: true })} over the range
        </span>
        <Sparkline values={values.map((v) => v.value)} />
      </div>
    </div>
  )
}

/** Patients as rows, metrics as columns, newest value in each cell. */
function TableWidget({ result }: { result: QueryResult }) {
  const metrics = useMetrics()
  if (!result.series.length) return <Empty />
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Patient</TableHead>
          {result.metrics.map((metric) => {
            const unit = shortUnit(metrics.get(metric)?.unit)
            return (
              <TableHead key={metric} className="text-right whitespace-normal">
                {metrics.label(metric)}
                {unit ? (
                  <span className="block text-[0.65rem] font-normal text-muted-foreground">
                    {unit}
                  </span>
                ) : null}
              </TableHead>
            )
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {result.series.map((series) => (
          <TableRow key={series.participant_id ?? series.display_name}>
            <TableCell className="font-medium">{series.display_name}</TableCell>
            {result.metrics.map((metric) => (
              <TableCell key={metric} className="text-right tabular-nums">
                {formatValue(metric, lastValue(series, metric))}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Patients by day for one metric: darker is higher, so a dip shows as a pale cell. */
function HeatmapWidget({ result }: { result: QueryResult }) {
  const metrics = useMetrics()
  const metric = result.metrics[0]
  const days = [
    ...new Set(
      result.series.flatMap((s) => valuesOf(s, metric).map((v) => v.t))
    ),
  ].sort()
  const all = result.series.flatMap((s) =>
    valuesOf(s, metric).map((v) => v.value)
  )
  if (!days.length) return <Empty />

  const [min, max] =
    metric === GLUCO_SCORE ? [0, 100] : [Math.min(...all), Math.max(...all)]
  const shade = (value: number) => 15 + 70 * ((value - min) / (max - min || 1))
  const dayLabel = (t: string) =>
    new Date(t).toLocaleDateString("en-US", {
      day: "numeric",
      timeZone: "UTC",
    })

  return (
    <div className="flex flex-col gap-2">
      <div
        className="grid items-center gap-1"
        style={{
          gridTemplateColumns: `4.5rem repeat(${days.length}, minmax(0, 1fr))`,
        }}
      >
        <span />
        {days.map((day) => (
          <span
            key={day}
            className="text-center text-[0.65rem] text-muted-foreground"
          >
            {dayLabel(day)}
          </span>
        ))}
        {result.series.map((series) => {
          const byDay = new Map(
            valuesOf(series, metric).map((v) => [v.t, v.value])
          )
          return (
            <div
              key={series.participant_id ?? series.display_name}
              className="contents"
            >
              <span className="truncate pr-1 text-xs">
                {series.display_name}
              </span>
              {days.map((day) => {
                const value = byDay.get(day)
                return (
                  <span
                    key={day}
                    title={`${series.display_name} · ${dayLabel(day)}: ${formatWithUnit(
                      metrics.get(metric),
                      metric,
                      value
                    )}`}
                    className="flex h-6 items-center justify-center rounded-sm text-[0.65rem] tabular-nums"
                    style={
                      value === undefined
                        ? { background: "var(--muted)" }
                        : {
                            background: `color-mix(in oklab, var(--primary) ${shade(value).toFixed(0)}%, transparent)`,
                          }
                    }
                  >
                    {value === undefined ? "" : formatValue(metric, value)}
                  </span>
                )
              })}
            </div>
          )
        })}
      </div>
      <p className="text-[0.65rem] text-muted-foreground">
        {metrics.label(metric)} by day (UTC) · darker is higher
      </p>
    </div>
  )
}

function Empty() {
  return <p className="text-sm text-muted-foreground">No readings yet.</p>
}

/** Draws a widget's data the way its kind calls for. */
export function WidgetView({
  kind,
  result,
  audience,
  height = 160,
}: {
  kind: Kind
  result: QueryResult
  audience: Audience
  height?: number
}) {
  switch (kind) {
    case "stat":
      return <StatWidget result={result} />
    case "table":
      return <TableWidget result={result} />
    case "heatmap":
      return <HeatmapWidget result={result} />
    default:
      return (
        <QueryChart
          result={result}
          snapshot
          hideNote
          showTitles={result.metrics.length > 1}
          height={height}
          audience={audience}
        />
      )
  }
}
