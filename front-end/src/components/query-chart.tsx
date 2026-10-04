"use client"

import { ChartLineIcon } from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts"

import { EstimateNote, type Audience } from "@/components/estimate-note"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import type { QueryResult } from "@/lib/api/events"
import { formatValue, GLUCO_SCORE, roundValue, useMetrics } from "@/lib/catalog"
import { formatReplayTime, formatTick } from "@/lib/format"
import { cn } from "@/lib/utils"

type Series = QueryResult["series"][number]

// Five validated categorical slots, assigned in order. Series past the fifth
// recede to a neutral line rather than inventing new hues.
const SLOTS = 5

function seriesColor(index: number) {
  return index < SLOTS ? `var(--chart-${index + 1})` : "var(--muted-foreground)"
}

function valueOf(
  point: Record<string, unknown>,
  metric: string
): number | null {
  const value = point[metric]
  return typeof value === "number" && Number.isFinite(value)
    ? roundValue(metric, value)
    : null
}

function hasValues(series: Series, metric: string) {
  return series.points.some((p) => valueOf(p, metric) !== null)
}

/** Rows keyed by time, one column per series, for a line chart. */
function pivot(series: Series[], metric: string) {
  const rows = new Map<string, Record<string, string | number | null>>()
  series.forEach((s, i) => {
    for (const point of s.points) {
      const t = String(point.t)
      const row = rows.get(t) ?? { t }
      row[`s${i}`] = valueOf(point, metric)
      rows.set(t, row)
    }
  })
  return [...rows.values()].sort((a, b) =>
    String(a.t).localeCompare(String(b.t))
  )
}

function PanelTitle({ metric }: { metric: string }) {
  const metrics = useMetrics()
  const info = metrics.get(metric)
  return (
    <div className="flex items-baseline gap-1.5 text-sm">
      <span className="font-medium">{info?.label ?? metric}</span>
      {info?.unit ? (
        <span className="text-xs text-muted-foreground">{info.unit}</span>
      ) : null}
    </div>
  )
}

function LinePanel({
  result,
  series,
  metric,
  height,
}: {
  result: QueryResult
  series: Series[]
  metric: string
  height: number
}) {
  const rows = pivot(series, metric)
  const config: ChartConfig = Object.fromEntries(
    series.map((s, i) => [
      `s${i}`,
      { label: s.display_name, color: seriesColor(i) },
    ])
  )
  const scaled = metric === GLUCO_SCORE && result.agg !== "delta"

  return (
    <ChartContainer
      config={config}
      className="aspect-auto w-full"
      style={{ height }}
    >
      <LineChart
        data={rows}
        margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        accessibilityLayer
      >
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="t"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          minTickGap={40}
          tickFormatter={(t: string) => formatTick(t, result.bucket)}
        />
        <YAxis
          width={44}
          tickLine={false}
          axisLine={false}
          domain={scaled ? [0, 100] : ["auto", "auto"]}
          tickFormatter={(v: number) => formatValue(metric, v)}
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(_, payload) =>
                formatReplayTime(payload?.[0]?.payload?.t)
              }
            />
          }
        />
        {series.length > 1 ? (
          <ChartLegend content={<ChartLegendContent />} />
        ) : null}
        {series.map((s, i) => (
          <Line
            key={s.participant_id ?? s.display_name}
            dataKey={`s${i}`}
            type="monotone"
            stroke={`var(--color-s${i})`}
            strokeWidth={2}
            dot={rows.length <= 12 ? { r: 3 } : false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ChartContainer>
  )
}

function BarPanel({
  result,
  series,
  metric,
}: {
  result: QueryResult
  series: Series[]
  metric: string
}) {
  const metrics = useMetrics()
  const rows = series.map((s) => ({
    name: s.display_name,
    value: valueOf(s.points.at(-1) ?? {}, metric),
  }))
  const config: ChartConfig = {
    value: { label: metrics.label(metric), color: "var(--chart-1)" },
  }
  const scaled = metric === GLUCO_SCORE && result.agg !== "delta"

  return (
    <ChartContainer
      config={config}
      className="aspect-auto w-full"
      style={{ height: Math.max(96, rows.length * 32 + 24) }}
    >
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
      >
        <CartesianGrid horizontal={false} />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tickLine={false}
          axisLine={false}
        />
        <XAxis
          type="number"
          domain={scaled ? [0, 100] : undefined}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => formatValue(metric, v)}
        />
        <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
        <Bar
          dataKey="value"
          fill="var(--color-value)"
          radius={4}
          isAnimationActive={false}
        />
      </BarChart>
    </ChartContainer>
  )
}

/**
 * Draws a POST /query result: one panel per metric (units never share an axis),
 * one line per series. Chat `data` events carry the same shape, so the
 * assistant's charts are drawn by this component too.
 */
export function QueryChart({
  result,
  snapshot = false,
  showTitles = true,
  height = 200,
  audience = "clinician",
  className,
}: {
  result: QueryResult
  /** A chat answer's chart: frozen at the time the assistant answered. */
  snapshot?: boolean
  showTitles?: boolean
  height?: number
  audience?: Audience
  className?: string
}) {
  const panels = result.metrics
    .map((metric) => ({
      metric,
      series: result.series.filter((s) => hasValues(s, metric)),
    }))
    .filter((panel) => panel.series.length > 0)

  if (panels.length === 0) {
    return (
      <Empty className={cn("border", className)}>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ChartLineIcon />
          </EmptyMedia>
          <EmptyTitle>No readings yet</EmptyTitle>
          <EmptyDescription>
            Nothing was recorded in this period up to now.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const asBars =
    result.bucket === "all" ||
    panels.every((p) => p.series.every((s) => s.points.length <= 1))

  return (
    <figure
      className={cn("@container/chart flex min-w-0 flex-col gap-3", className)}
    >
      <div
        className={cn(
          "grid gap-x-6 gap-y-5",
          panels.length > 1 && "@lg/chart:grid-cols-2",
          panels.length > 2 && "@4xl/chart:grid-cols-3"
        )}
      >
        {panels.map(({ metric, series }) => (
          <div key={metric} className="flex min-w-0 flex-col gap-2">
            {showTitles || panels.length > 1 ? (
              <PanelTitle metric={metric} />
            ) : null}
            {asBars ? (
              <BarPanel result={result} series={series} metric={metric} />
            ) : (
              <LinePanel
                result={result}
                series={series}
                metric={metric}
                height={height}
              />
            )}
          </div>
        ))}
      </div>
      <figcaption className="flex flex-col gap-1">
        {result.truncated ? (
          <span className="text-xs text-muted-foreground">
            Showing {result.series.length} of {result.total_series} series.
          </span>
        ) : null}
        {snapshot && result.as_of ? (
          <span className="text-xs text-muted-foreground">
            Snapshot as of {formatReplayTime(result.as_of)} UTC
          </span>
        ) : null}
        {result.metrics.includes(GLUCO_SCORE) ? (
          <EstimateNote audience={audience} />
        ) : null}
      </figcaption>
    </figure>
  )
}
