"use client"

import { PinOffIcon, ShieldCheckIcon } from "lucide-react"
import { toast } from "sonner"

import type { Audience } from "@/components/estimate-note"
import { WidgetView } from "@/components/widgets/widget-view"
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
import { friendlyError, type Schemas } from "@/lib/api/client"
import {
  usePinnedWidgets,
  useUnpinWidget,
  useWidgetData,
} from "@/lib/api/queries"
import { useMetrics } from "@/lib/catalog"

type PinnedWidget = Schemas["PinnedWidget"]

const KIND_LABELS: Record<PinnedWidget["kind"], string> = {
  trend: "Trend",
  ranking: "Ranking",
  cohort_trend: "Panel trend",
  stat: "Stat",
  table: "Table",
  heatmap: "Heatmap",
}

function PinnedWidgetCard({
  pin,
  audience,
}: {
  pin: PinnedWidget
  audience: Audience
}) {
  const metrics = useMetrics()
  const data = useWidgetData(pin.id, metrics.anyLive(pin.query.metrics ?? []))
  const unpin = useUnpinWidget()
  const compliance = data.data?.steps.find((s) => s.stage === "compliance")

  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="text-sm">{pin.title}</CardTitle>
        <CardDescription className="text-xs">
          {KIND_LABELS[pin.kind]} · live, last {pin.query.hours ?? 168} h
        </CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Unpin ${pin.title}`}
            disabled={unpin.isPending}
            onClick={() =>
              unpin.mutate(pin.id, {
                onError: (error) => toast.error(friendlyError(error)),
              })
            }
          >
            <PinOffIcon />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {data.data ? (
          <WidgetView
            kind={pin.kind}
            result={data.data.result}
            audience={audience}
            height={180}
          />
        ) : data.isError ? (
          <p className="text-sm text-muted-foreground">
            {friendlyError(data.error)}
          </p>
        ) : (
          <Skeleton className="h-[180px] w-full" />
        )}
        {compliance ? (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <ShieldCheckIcon
              aria-hidden
              className="mt-px size-3.5 shrink-0 text-primary"
            />
            {compliance.text}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** Widgets the user pinned from the chat. Hidden until there is one. */
export function PinnedWidgets({ audience }: { audience: Audience }) {
  const pins = usePinnedWidgets()
  if (!pins.data?.length) return null

  return (
    <section aria-labelledby="pinned-heading" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2
          id="pinned-heading"
          className="text-lg font-semibold tracking-tight"
        >
          Pinned widgets
        </h2>
        <p className="text-sm text-muted-foreground">
          {audience === "patient"
            ? "Charts you asked Gluco to keep here. They update as new readings come in."
            : "Built by Gluco from your requests. Each one re-runs its query and compliance check as new data streams in."}
        </p>
      </div>
      <div className="grid gap-4 @2xl/main:grid-cols-2 @5xl/main:grid-cols-3">
        {pins.data.map((pin) => (
          <PinnedWidgetCard key={pin.id} pin={pin} audience={audience} />
        ))}
      </div>
    </section>
  )
}
