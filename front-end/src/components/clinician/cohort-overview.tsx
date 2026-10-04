"use client"

import { TriangleAlertIcon } from "lucide-react"
import Link from "next/link"

import { participantHref } from "@/components/clinician/links"
import { EstimateNote } from "@/components/estimate-note"
import { ChangeBadge } from "@/components/gluco-score"
import { QueryChart } from "@/components/query-chart"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { friendlyError, type Schemas } from "@/lib/api/client"
import { useCohort, useSeries, type QuerySpec } from "@/lib/api/queries"
import { formatValue, GLUCO_CHANGE, GLUCO_SCORE } from "@/lib/catalog"

type ParticipantRow = Schemas["ParticipantRow"]

const COHORT_TREND: QuerySpec = {
  metrics: [GLUCO_SCORE],
  group_by: "cohort",
  hours: 168,
  bucket: "hour",
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-baseline gap-2">
        <span className="text-3xl font-bold tracking-tight">
          {value}
        </span>
        {hint ? (
          <span className="text-xs text-muted-foreground">{hint}</span>
        ) : null}
      </CardContent>
    </Card>
  )
}

function RowList({
  title,
  description,
  rows,
}: {
  title: string
  description: string
  rows: ParticipantRow[]
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No patients to show yet.</p>
        ) : (
          <ItemGroup className="gap-1">
            {rows.map((row) => (
              <Item key={row.person_id} size="xs" asChild>
                <Link href={participantHref(row.person_id)}>
                  <ItemContent>
                    <ItemTitle>{row.display_name}</ItemTitle>
                    <ItemDescription className="tabular-nums">
                      Gluco Score{" "}
                      {formatValue(GLUCO_SCORE, row.values[GLUCO_SCORE])}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <ChangeBadge change={row.values[GLUCO_CHANGE]} />
                  </ItemActions>
                </Link>
              </Item>
            ))}
          </ItemGroup>
        )}
      </CardContent>
    </Card>
  )
}

/** GET /cohort plus the pooled Gluco trend. Clinicians only. */
export function CohortOverview() {
  const cohort = useCohort()
  const trend = useSeries(COHORT_TREND)

  if (cohort.isError) {
    return (
      <Alert variant="destructive">
        <TriangleAlertIcon />
        <AlertTitle>Couldn&apos;t load your patient panel</AlertTitle>
        <AlertDescription>{friendlyError(cohort.error)}</AlertDescription>
      </Alert>
    )
  }

  const data = cohort.data
  const gluco = data?.gluco_score

  return (
    <section className="flex flex-col gap-4" aria-label="Patient panel overview">
      <div className="grid gap-4 @xl/main:grid-cols-2 @4xl/main:grid-cols-4">
        {data ? (
          <>
            <Stat label="Patients" value={String(data.participants)} />
            <Stat
              label="Median Gluco Score"
              value={formatValue(GLUCO_SCORE, gluco?.median)}
              hint={
                gluco
                  ? `Mean ${formatValue(GLUCO_SCORE, gluco.mean)}`
                  : undefined
              }
            />
            <Stat
              label="Lowest Gluco Score"
              value={formatValue(GLUCO_SCORE, gluco?.min)}
            />
            <Stat
              label="Highest Gluco Score"
              value={formatValue(GLUCO_SCORE, gluco?.max)}
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))
        )}
      </div>
      <EstimateNote />

      <div className="grid gap-4 @4xl/main:grid-cols-3">
        {data ? (
          <>
            <RowList
              title="Lowest Gluco Score"
              description="Most recent 24 h window, lowest first."
              rows={data.lowest_gluco}
            />
            <RowList
              title="Largest 24 h declines"
              description="Greatest decline since this time yesterday."
              rows={data.biggest_drops}
            />
            <RowList
              title="Largest 24 h increases"
              description="Greatest increase since this time yesterday."
              rows={data.biggest_gains}
            />
          </>
        ) : (
          Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-56" />
          ))
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Panel Gluco Score, last 7 days</CardTitle>
          <CardDescription>
            Hourly mean across all patients.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trend.data ? (
            <QueryChart result={trend.data} showTitles={false} height={220} />
          ) : trend.isError ? (
            <p className="text-sm text-destructive">{friendlyError(trend.error)}</p>
          ) : (
            <Skeleton className="h-56" />
          )}
        </CardContent>
      </Card>
    </section>
  )
}
