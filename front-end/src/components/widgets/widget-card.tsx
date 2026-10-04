"use client"

import {
  CheckIcon,
  DatabaseIcon,
  PaletteIcon,
  PinIcon,
  RadioIcon,
  ShieldCheckIcon,
} from "lucide-react"
import { toast } from "sonner"

import type { Audience } from "@/components/estimate-note"
import { WidgetView } from "@/components/widgets/widget-view"
import { Button } from "@/components/ui/button"
import { friendlyError } from "@/lib/api/client"
import type { ChatWidget, QueryResult, WidgetStep } from "@/lib/api/events"
import { usePinWidget } from "@/lib/api/queries"
import { cn } from "@/lib/utils"

const STAGES: Record<
  WidgetStep["stage"],
  { label: string; icon: typeof PinIcon }
> = {
  design: { label: "Design", icon: PaletteIcon },
  fetch: { label: "Fetch", icon: DatabaseIcon },
  compliance: { label: "Compliance", icon: ShieldCheckIcon },
  bind: { label: "Live", icon: RadioIcon },
}

/** The pipeline that built a widget, one line per stage. */
export function WidgetSteps({ steps }: { steps: WidgetStep[] }) {
  return (
    <ol
      className="flex flex-col gap-1.5"
      aria-label="How this widget was built"
    >
      {steps.map((step) => {
        const { label, icon: Icon } = STAGES[step.stage]
        const compliance = step.stage === "compliance"
        return (
          <li
            key={step.stage}
            className={cn(
              "flex items-start gap-2 text-xs text-muted-foreground",
              compliance && "text-foreground"
            )}
          >
            <Icon
              aria-hidden
              className={cn(
                "mt-px size-3.5 shrink-0",
                compliance && "text-primary"
              )}
            />
            <span>
              <span className="font-medium text-foreground">{label}</span>
              {" · "}
              {step.text}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** A widget the agent built in chat: its chart, its pipeline, and a Pin button. */
export function WidgetCard({
  widget,
  chart,
  audience,
}: {
  widget: ChatWidget
  chart: QueryResult
  audience: Audience
}) {
  const pin = usePinWidget()
  const pinned = pin.isSuccess

  const onPin = () =>
    pin.mutate(
      { title: widget.title, kind: widget.kind, query: widget.query },
      {
        onSuccess: () =>
          toast.success(`Pinned “${widget.title}” to your dashboard`),
        onError: (error) => toast.error(friendlyError(error)),
      }
    )

  return (
    <div className="@container/widget flex w-full flex-col gap-3 rounded-lg border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-[0.7rem] font-medium tracking-wide text-muted-foreground uppercase">
            Widget
          </span>
          <h3 className="text-sm leading-snug font-semibold">{widget.title}</h3>
        </div>
        <Button
          size="sm"
          variant={pinned ? "secondary" : "default"}
          disabled={pin.isPending || pinned}
          onClick={onPin}
        >
          {pinned ? (
            <CheckIcon data-icon="inline-start" />
          ) : (
            <PinIcon data-icon="inline-start" />
          )}
          {pinned ? "Pinned" : "Pin"}
        </Button>
      </div>
      <WidgetView kind={widget.kind} result={chart} audience={audience} />
      <div className="border-t pt-2.5">
        <WidgetSteps steps={widget.steps} />
      </div>
    </div>
  )
}
