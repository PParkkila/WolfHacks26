"use client"

import { TriangleAlertIcon } from "lucide-react"

import { GlucoScore } from "@/components/gluco-score"
import { QueryChart } from "@/components/query-chart"
import { PRIMARY_VITALS, ReadingRow, VitalTile } from "@/components/vitals"
import { WhatChanged } from "@/components/what-changed"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { friendlyError } from "@/lib/api/client"
import { useExplain, useParticipant, useSeries } from "@/lib/api/queries"
import { GLUCO_CHANGE, GLUCO_SCORE, useMetrics } from "@/lib/catalog"
import { useClock } from "@/lib/clock"
import { formatReplayTime } from "@/lib/format"
import type { Principal } from "@/lib/session"

const PRIMARY = new Set(PRIMARY_VITALS.map((v) => v.metric))

function SectionHeading({
  id,
  title,
  description,
}: {
  id: string
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <h2 id={id} className="text-lg font-semibold tracking-tight">
        {title}
      </h2>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
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
  const score = useSeries({
    metrics: [GLUCO_SCORE],
    participants: [me],
    hours: 168,
    bucket: "day",
    agg: "mean",
  })
  const sensorWeek = useSeries(
    {
      metrics: metrics.sensors.map((m) => m.name),
      participants: [me],
      hours: 168,
      bucket: "day",
      agg: "mean",
    },
    metrics.ready
  )

  const values = latest.data?.values
  const changeFor = (metric: string) =>
    explain.data?.change.changes.find((c) => c.metric === metric)
  const others = metrics.sensors.filter((m) => !PRIMARY.has(m.name))
  const ready = metrics.ready && values

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
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
          <AlertDescription>{friendlyError(latest.error)}</AlertDescription>
        </Alert>
      ) : null}

      <Card className="gap-0 p-0 @3xl/main:flex-row">
        <section
          aria-labelledby="score-heading"
          className="flex flex-col gap-4 p-6 @3xl/main:w-80 @3xl/main:shrink-0 @3xl/main:border-r"
        >
          <SectionHeading
            id="score-heading"
            title="Your Gluco Score"
            description="From the last 24 hours of your wearable data."
          />
          {values ? (
            <GlucoScore
              value={values[GLUCO_SCORE]}
              change={values[GLUCO_CHANGE]}
              audience="patient"
            />
          ) : (
            <Skeleton className="h-48" />
          )}
        </section>
        <section
          aria-labelledby="week-heading"
          className="flex min-w-0 flex-1 flex-col gap-4 border-t p-6 @3xl/main:border-t-0"
        >
          <SectionHeading
            id="week-heading"
            title="Your week"
            description="Your average Gluco Score for each day."
          />
          {score.data ? (
            <QueryChart
              result={score.data}
              showTitles={false}
              height={220}
              audience="patient"
              hideNote
            />
          ) : (
            <Skeleton className="h-56" />
          )}
        </section>
      </Card>

      <section className="flex flex-col gap-4" aria-labelledby="vitals-heading">
        <SectionHeading
          id="vitals-heading"
          title="Your vitals"
          description="The last 24 hours, compared with your own usual week."
        />
        <div className="grid gap-4 @3xl/main:grid-cols-3">
          {ready
            ? PRIMARY_VITALS.map((vital) => (
                <VitalTile
                  key={vital.metric}
                  {...vital}
                  info={metrics.get(vital.metric)}
                  value={values[vital.metric]}
                  change={changeFor(vital.metric)}
                  week={sensorWeek.data}
                />
              ))
            : PRIMARY_VITALS.map((vital) => (
                <Skeleton key={vital.metric} className="h-60 rounded-2xl" />
              ))}
        </div>
      </section>

      {others.length ? (
        <section
          className="flex flex-col gap-4"
          aria-labelledby="readings-heading"
        >
          <SectionHeading
            id="readings-heading"
            title="More from your wearable"
            description="How your movement and temperature patterns varied."
          />
          <Card className="grid gap-3 p-4 @2xl/main:grid-cols-2">
            {ready
              ? others.map((metric) => (
                  <ReadingRow
                    key={metric.name}
                    metric={metric.name}
                    info={metric}
                    value={values[metric.name]}
                    change={changeFor(metric.name)}
                  />
                ))
              : others.map((metric) => (
                  <Skeleton key={metric.name} className="h-28 rounded-xl" />
                ))}
          </Card>
        </section>
      ) : null}

      <WhatChanged personId={me} audience="patient" />
    </div>
  )
}
