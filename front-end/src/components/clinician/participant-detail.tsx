"use client"

import { ArrowLeftIcon, UserRoundXIcon } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { GlucoScore } from "@/components/gluco-score"
import { QueryChart } from "@/components/query-chart"
import { WhatChanged } from "@/components/what-changed"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { friendlyError } from "@/lib/api/client"
import type { QueryResult } from "@/lib/api/events"
import { useParticipant, useSeries } from "@/lib/api/queries"
import { GLUCO_CHANGE, GLUCO_SCORE, useMetrics } from "@/lib/catalog"
import { formatReplayTime } from "@/lib/format"

const RANGES = [
  { hours: 24, label: "24 h" },
  { hours: 72, label: "72 h" },
  { hours: 168, label: "7 d" },
]

function ChartBody({
  query,
  height,
  showTitles,
}: {
  query: { data?: QueryResult; isError: boolean; error: Error | null }
  height: number
  showTitles: boolean
}) {
  if (query.data)
    return (
      <QueryChart result={query.data} height={height} showTitles={showTitles} />
    )
  if (query.isError)
    return <p className="text-sm text-destructive">{query.error?.message}</p>
  return <Skeleton style={{ height }} />
}

export function ParticipantDetail({ id }: { id: string }) {
  const metrics = useMetrics()
  const participant = useParticipant(id)
  const [hours, setHours] = useState(168)

  const gluco = useSeries({
    metrics: [GLUCO_SCORE],
    participants: [id],
    hours,
    bucket: "hour",
  })
  const sensors = useSeries(
    {
      metrics: metrics.sensors.map((m) => m.name),
      participants: [id],
      hours,
      bucket: "hour",
    },
    metrics.ready
  )

  const back = (
    <Button variant="ghost" size="sm" asChild className="self-start">
      <Link href="/clinician">
        <ArrowLeftIcon data-icon="inline-start" />
        All patients
      </Link>
    </Button>
  )

  if (participant.isError) {
    return (
      <div className="flex flex-col gap-4">
        {back}
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <UserRoundXIcon />
            </EmptyMedia>
            <EmptyTitle>Patient not found</EmptyTitle>
            <EmptyDescription>{friendlyError(participant.error)}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant="outline" size="sm" asChild>
              <Link href="/clinician">Back to patient panel</Link>
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    )
  }

  const row = participant.data
  const range = (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      value={String(hours)}
      onValueChange={(value) => value && setHours(Number(value))}
      aria-label="Time range"
    >
      {RANGES.map((r) => (
        <ToggleGroupItem key={r.hours} value={String(r.hours)}>
          {r.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        {back}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {row ? (
            <>
              <h1 className="text-2xl font-bold tracking-tight">
                {row.display_name}
              </h1>
              <span className="text-sm text-muted-foreground">
                Latest 24 h window ends {formatReplayTime(row.window_end)} UTC
              </span>
            </>
          ) : (
            <Skeleton className="h-8 w-64" />
          )}
          <div className="ml-auto">{range}</div>
        </div>
      </div>

      <div className="grid gap-4 @4xl/main:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Gluco Score</CardTitle>
            <CardDescription>Most recent 24 h window</CardDescription>
          </CardHeader>
          <CardContent>
            {row ? (
              <GlucoScore
                value={row.values[GLUCO_SCORE]}
                change={row.values[GLUCO_CHANGE]}
                audience="clinician"
              />
            ) : (
              <Skeleton className="h-40" />
            )}
          </CardContent>
        </Card>
        <Card className="@4xl/main:col-span-2">
          <CardHeader>
            <CardTitle>Gluco Score trend</CardTitle>
            <CardDescription>Hourly, up to the time shown.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartBody query={gluco} height={220} showTitles={false} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Sensor trends</CardTitle>
          <CardDescription>
            Each point reflects the preceding 24 hours.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartBody query={sensors} height={160} showTitles />
        </CardContent>
      </Card>

      <WhatChanged personId={id} audience="clinician" />
    </div>
  )
}
