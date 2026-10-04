"use client"

import { InfoIcon, TriangleAlertIcon } from "lucide-react"

import { GlucoScore } from "@/components/gluco-score"
import { QueryChart } from "@/components/query-chart"
import { WhatChanged } from "@/components/what-changed"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useExplain, useParticipant, useSeries } from "@/lib/api/queries"
import {
  formatWithUnit,
  GLUCO_CHANGE,
  GLUCO_SCORE,
  useMetrics,
} from "@/lib/catalog"
import { useClock } from "@/lib/clock"
import { formatReplayTime } from "@/lib/format"
import type { Principal } from "@/lib/session"

function usualPhrase(z: number | null | undefined): string {
  if (z == null) return "Not enough readings to compare yet"
  const size = Math.abs(z)
  if (size < 1) return "Close to your usual"
  return `${size >= 2 ? "A lot" : "A bit"} ${z > 0 ? "higher" : "lower"} than usual for you`
}

/**
 * A patient's own view. It only ever asks for this person's data, so nothing
 * cohort-wide is requested or rendered.
 */
export function PatientDashboard({ principal }: { principal: Principal }) {
  const me = principal.participant_id ?? ""
  const { clock } = useClock()
  const metrics = useMetrics()
  const latest = useParticipant(me)
  const explain = useExplain(me, 24)
  const week = useSeries({
    metrics: [GLUCO_SCORE],
    participants: [me],
    hours: 168,
    bucket: "day",
    agg: "mean",
  })

  const values = latest.data?.values
  const changeFor = (metric: string) =>
    explain.data?.change.changes.find((c) => c.metric === metric)

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Hi, {principal.display_name}
        </h1>
        <p className="text-muted-foreground">
          Here&apos;s how your week looks
          {clock?.now ? `, as of ${formatReplayTime(clock.now)}` : ""}.
        </p>
      </header>

      {latest.isError ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>We couldn&apos;t load your readings</AlertTitle>
          <AlertDescription>{latest.error.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 @4xl/main:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Your Gluco Score</CardTitle>
            <CardDescription>
              From the last 24 hours of your wearable data.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {values ? (
              <GlucoScore
                value={values[GLUCO_SCORE]}
                change={values[GLUCO_CHANGE]}
                audience="patient"
              />
            ) : (
              <Skeleton className="h-40" />
            )}
          </CardContent>
        </Card>
        <Card className="@4xl/main:col-span-2">
          <CardHeader>
            <CardTitle>Your week</CardTitle>
            <CardDescription>
              Your average Gluco Score for each day.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {week.data ? (
              <QueryChart
                result={week.data}
                showTitles={false}
                height={220}
                audience="patient"
              />
            ) : (
              <Skeleton className="h-56" />
            )}
          </CardContent>
        </Card>
      </div>

      <section className="flex flex-col gap-3" aria-labelledby="sensor-heading">
        <div className="flex flex-col gap-1">
          <h2
            id="sensor-heading"
            className="text-lg font-semibold tracking-tight"
          >
            Your sensor readings
          </h2>
          <p className="text-sm text-muted-foreground">
            What your wearable measured over the last 24 hours.
          </p>
        </div>
        <div className="grid gap-4 @xl/main:grid-cols-2 @4xl/main:grid-cols-3">
          {metrics.ready && values
            ? metrics.sensors.map((metric) => (
                <Card key={metric.name} size="sm">
                  <CardHeader>
                    <HoverCard openDelay={150}>
                      <HoverCardTrigger asChild>
                        <button
                          type="button"
                          className="flex items-center gap-1.5 text-left text-sm text-muted-foreground"
                        >
                          {metric.label}
                          <InfoIcon className="size-3.5" />
                        </button>
                      </HoverCardTrigger>
                      <HoverCardContent className="text-sm">
                        {metric.description}
                      </HoverCardContent>
                    </HoverCard>
                  </CardHeader>
                  <CardContent>
                    <span className="text-2xl font-semibold tracking-tight tabular-nums">
                      {formatWithUnit(metric, metric.name, values[metric.name])}
                    </span>
                  </CardContent>
                  <CardFooter>
                    <span className="text-xs text-muted-foreground">
                      {explain.data
                        ? usualPhrase(changeFor(metric.name)?.z_vs_baseline)
                        : "Comparing with your usual…"}
                    </span>
                  </CardFooter>
                </Card>
              ))
            : Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
        </div>
      </section>

      <WhatChanged personId={me} audience="patient" />
    </div>
  )
}
