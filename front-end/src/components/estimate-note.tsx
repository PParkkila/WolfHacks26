"use client"

import { InfoIcon } from "lucide-react"

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { GLUCO_SCORE, useMetrics } from "@/lib/catalog"

export type Audience = "clinician" | "patient"

/** Shown wherever a Gluco Score is: it is an estimate, never a diagnosis. */
export function EstimateNote({
  audience = "clinician",
  className,
}: {
  audience?: Audience
  className?: string
}) {
  const metrics = useMetrics()
  const description = metrics.get(GLUCO_SCORE)?.description
  return (
    <p
      className={cn(
        "flex items-start gap-1.5 text-xs text-muted-foreground",
        className
      )}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label="About the Gluco Score"
            className="mt-px"
          >
            <InfoIcon className="size-3.5" />
          </button>
        </TooltipTrigger>
        {description ? (
          <TooltipContent className="max-w-72">{description}</TooltipContent>
        ) : null}
      </Tooltip>
      {audience === "patient"
        ? "Your Gluco Score is an estimate from your wearable, not a medical diagnosis."
        : "The Gluco Score is a model estimate. It is not a glucose measurement or a diagnosis."}
    </p>
  )
}
