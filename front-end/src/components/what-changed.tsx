"use client"

import {
  ArrowDownIcon,
  ArrowUpIcon,
  MinusIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { useState } from "react"

import type { Audience } from "@/components/estimate-note"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { Schemas } from "@/lib/api/client"
import { useExplain } from "@/lib/api/queries"
import {
  formatWithUnit,
  GLUCO_CHANGE,
  GLUCO_SCORE,
  useMetrics,
} from "@/lib/catalog"
import { formatReplayTime } from "@/lib/format"

type MetricChange = Schemas["MetricChange"]
type ChangeReport = Schemas["ChangeReport"]
type FeatureDeviation = Schemas["FeatureDeviation"]

const WINDOWS: Record<Audience, { hours: number; label: string }[]> = {
  clinician: [
    { hours: 24, label: "24 h" },
    { hours: 48, label: "48 h" },
    { hours: 72, label: "72 h" },
  ],
  patient: [
    { hours: 24, label: "Yesterday" },
    { hours: 72, label: "3 days ago" },
  ],
}

function UsualBadge({ z }: { z: number | null | undefined }) {
  if (z == null) return <span className="text-muted-foreground">—</span>
  const size = Math.abs(z)
  const label = size >= 2 ? "Unusual" : size >= 1 ? "Somewhat" : "Typical"
  return (
    <span className="flex items-center justify-end gap-2">
      <span className="font-mono text-xs text-muted-foreground">
        z {z > 0 ? "+" : ""}
        {z.toFixed(1)}
      </span>
      <Badge
        variant={size >= 2 ? "default" : size >= 1 ? "secondary" : "outline"}
      >
        {label}
      </Badge>
    </span>
  )
}

function DirectionIcon({ value }: { value: number | null | undefined }) {
  if (value == null || value === 0) return <MinusIcon className="size-3.5" />
  return value > 0 ? (
    <ArrowUpIcon className="size-3.5" />
  ) : (
    <ArrowDownIcon className="size-3.5" />
  )
}

function ClinicianChanges({
  report,
  cohort,
}: {
  report: ChangeReport
  cohort: FeatureDeviation[] | null | undefined
}) {
  const metrics = useMetrics()
  const shifts = new Set(report.largest_shifts)
  const rows = report.changes.filter((c) => c.metric !== GLUCO_CHANGE)

  return (
    <div className="flex flex-col gap-6">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Metric</TableHead>
            <TableHead className="text-right">{report.hours} h ago</TableHead>
            <TableHead className="text-right">Now</TableHead>
            <TableHead className="text-right">Change</TableHead>
            <TableHead className="text-right">vs own week</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((c) => {
            const info = metrics.get(c.metric)
            const better =
              info?.higher_is_better == null || c.delta == null || c.delta === 0
                ? null
                : c.delta > 0 === info.higher_is_better
            return (
              <TableRow
                key={c.metric}
                data-state={shifts.has(c.metric) ? "selected" : undefined}
              >
                <TableCell>
                  <span className="flex items-center gap-2">
                    {info?.label ?? c.label}
                    {shifts.has(c.metric) ? (
                      <Badge variant="outline">Top shift</Badge>
                    ) : null}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {formatWithUnit(info, c.metric, c.then)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatWithUnit(info, c.metric, c.now)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <span className="flex items-center justify-end gap-1">
                    <DirectionIcon value={c.delta} />
                    {formatWithUnit(info, c.metric, c.delta, { signed: true })}
                    {better === null ? null : (
                      <Badge
                        variant={better ? "secondary" : "destructive"}
                        className="ml-1"
                      >
                        {better ? "better" : "worse"}
                      </Badge>
                    )}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <UsualBadge z={c.z_vs_baseline} />
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>

      {cohort?.length ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Where they sit in the cohort</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="text-right">Cohort median</TableHead>
                <TableHead className="text-right">Percentile</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cohort.map((d) => {
                const info = metrics.get(d.feature)
                return (
                  <TableRow key={d.feature}>
                    <TableCell>{info?.label ?? d.feature}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatWithUnit(info, d.feature, d.value)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatWithUnit(info, d.feature, d.median)}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="flex items-center justify-end gap-1 tabular-nums">
                        <DirectionIcon value={d.z_score} />
                        {Math.round(d.percentile)}th
                      </span>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </div>
  )
}

function sentence(change: MetricChange, label: string) {
  const name = label.charAt(0).toLowerCase() + label.slice(1)
  const z = change.z_vs_baseline
  if (z == null || Math.abs(z) < 1)
    return `Your ${name} is close to your usual.`
  const amount = Math.abs(z) >= 2 ? "a lot" : "a bit"
  return `Your ${name} is ${amount} ${z > 0 ? "higher" : "lower"} than usual for you.`
}

function PatientChanges({
  report,
  since,
}: {
  report: ChangeReport
  since: string
}) {
  const metrics = useMetrics()
  const shifts = report.largest_shifts
  const rows = report.changes
    .filter((c) => c.metric !== GLUCO_SCORE && c.metric !== GLUCO_CHANGE)
    .sort((a, b) => {
      const rank = (c: MetricChange) => {
        const i = shifts.indexOf(c.metric)
        return i === -1 ? shifts.length : i
      }
      return (
        rank(a) - rank(b) ||
        Math.abs(b.z_vs_baseline ?? 0) - Math.abs(a.z_vs_baseline ?? 0)
      )
    })

  return (
    <ItemGroup className="gap-2">
      {rows.map((c) => {
        const info = metrics.get(c.metric)
        return (
          <Item key={c.metric} variant="muted" size="sm">
            <ItemMedia variant="icon">
              <DirectionIcon
                value={
                  Math.abs(c.z_vs_baseline ?? 0) >= 1 ? c.z_vs_baseline : 0
                }
              />
            </ItemMedia>
            <ItemContent>
              <ItemTitle>{sentence(c, info?.label ?? c.label)}</ItemTitle>
              <ItemDescription>
                {c.delta == null
                  ? "Not enough readings to compare yet."
                  : `${formatWithUnit(info, c.metric, c.delta, { signed: true })} compared with ${since}.`}
              </ItemDescription>
            </ItemContent>
          </Item>
        )
      })}
    </ItemGroup>
  )
}

/** GET /participants/{id}/explain: how each metric moved, and how unusual that is. */
export function WhatChanged({
  personId,
  audience,
}: {
  personId: string
  audience: Audience
}) {
  const options = WINDOWS[audience]
  const [hours, setHours] = useState(options[0].hours)
  const explain = useExplain(personId, hours)
  const since =
    options.find((o) => o.hours === hours)?.label.toLowerCase() ??
    `${hours} h ago`

  return (
    <Card>
      <CardHeader>
        <CardTitle>What changed</CardTitle>
        <CardDescription>
          {audience === "patient"
            ? "How your readings compare with your own usual week."
            : explain.data
              ? `Latest window (${formatReplayTime(explain.data.change.now_window_end)}) vs ${hours} h earlier and vs their own last 7 days.`
              : "Latest window vs earlier, and vs their own last 7 days."}
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            size="sm"
            variant="outline"
            value={String(hours)}
            onValueChange={(value) => value && setHours(Number(value))}
            aria-label="Compare with"
          >
            {options.map((o) => (
              <ToggleGroupItem key={o.hours} value={String(o.hours)}>
                {o.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </CardAction>
      </CardHeader>
      <CardContent>
        {explain.isError ? (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertDescription>{explain.error.message}</AlertDescription>
          </Alert>
        ) : !explain.data ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : audience === "patient" ? (
          <PatientChanges report={explain.data.change} since={since} />
        ) : (
          <ClinicianChanges
            report={explain.data.change}
            cohort={explain.data.cohort_position}
          />
        )}
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">
          {audience === "patient"
            ? "These are patterns that moved together, not causes. Your Gluco Score is an estimate, not a diagnosis."
            : (explain.data?.change.note ??
              "These are associations, not causes. The Gluco Score is a model estimate, not a diagnosis.")}
        </p>
      </CardFooter>
    </Card>
  )
}
