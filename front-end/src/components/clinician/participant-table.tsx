"use client"

import {
  ArrowDownIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  TriangleAlertIcon,
} from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { participantHref } from "@/components/clinician/links"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { friendlyError } from "@/lib/api/client"
import { useParticipants, type SortOrder } from "@/lib/api/queries"
import {
  formatValue,
  GLUCO_CHANGE,
  GLUCO_SCORE,
  useMetrics,
  type MetricInfo,
} from "@/lib/catalog"
import { formatReplayTime } from "@/lib/format"
import { cn } from "@/lib/utils"

type Sort = { by: string; order: SortOrder }

function SortHeader({
  metric,
  sort,
  onSort,
}: {
  metric: MetricInfo
  sort: Sort
  onSort: (metric: string) => void
}) {
  const active = sort.by === metric.name
  const Icon = !active
    ? ArrowUpDownIcon
    : sort.order === "asc"
      ? ArrowUpIcon
      : ArrowDownIcon
  return (
    <TableHead
      className="text-right"
      aria-sort={
        active ? (sort.order === "asc" ? "ascending" : "descending") : "none"
      }
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "-mr-2 h-auto min-w-24 py-1 whitespace-normal",
              !active && "text-muted-foreground"
            )}
            onClick={() => onSort(metric.name)}
          >
            <span className="flex flex-col items-end text-right leading-tight">
              <span>{metric.label}</span>
              <span className="text-xs font-normal text-muted-foreground">
                {metric.unit}
              </span>
            </span>
            <Icon data-icon="inline-end" />
          </Button>
        </TooltipTrigger>
        <TooltipContent className="max-w-64">
          {metric.description}
        </TooltipContent>
      </Tooltip>
    </TableHead>
  )
}

/** GET /participants: newest values per participant, sortable by any metric (server-side). */
export function ParticipantTable() {
  const router = useRouter()
  const metrics = useMetrics()
  const [sort, setSort] = useState<Sort>({ by: GLUCO_SCORE, order: "asc" })
  const participants = useParticipants(sort.by, sort.order)

  const onSort = (metric: string) =>
    setSort((prev) =>
      prev.by === metric
        ? { by: metric, order: prev.order === "asc" ? "desc" : "asc" }
        : { by: metric, order: "asc" }
    )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Patients</CardTitle>
        <CardDescription>
          Most recent 24 h window for each patient. Select a column to sort;
          select a row for detail.
        </CardDescription>
        <CardAction>{participants.isFetching ? <Spinner /> : null}</CardAction>
      </CardHeader>
      <CardContent>
        {participants.isError ? (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertDescription>{friendlyError(participants.error)}</AlertDescription>
          </Alert>
        ) : !participants.data || !metrics.ready ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="align-bottom">Patient</TableHead>
                {metrics.list.map((metric) => (
                  <SortHeader
                    key={metric.name}
                    metric={metric}
                    sort={sort}
                    onSort={onSort}
                  />
                ))}
                <TableHead className="text-right align-bottom">
                  Latest reading
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {participants.data.map((row) => (
                <TableRow
                  key={row.person_id}
                  className="cursor-pointer"
                  onClick={() => router.push(participantHref(row.person_id))}
                >
                  <TableCell className="font-medium">
                    <Link
                      href={participantHref(row.person_id)}
                      onClick={(event) => event.stopPropagation()}
                      className="hover:underline"
                    >
                      {row.display_name}
                    </Link>
                  </TableCell>
                  {metrics.list.map((metric) => (
                    <TableCell
                      key={metric.name}
                      className={cn(
                        "text-right tabular-nums",
                        metric.name === GLUCO_SCORE && "font-semibold",
                        sort.by === metric.name && "bg-muted/50"
                      )}
                    >
                      {formatValue(metric.name, row.values[metric.name], {
                        signed: metric.name === GLUCO_CHANGE,
                      })}
                    </TableCell>
                  ))}
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {formatReplayTime(row.window_end)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
