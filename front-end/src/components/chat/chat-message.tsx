"use client"

import { CheckIcon, TriangleAlertIcon } from "lucide-react"

import type {
  ChatMessage as ChatMessageType,
  ChatPart,
} from "@/components/chat/chat-provider"
import { Markdown } from "@/components/chat/markdown"
import type { Audience } from "@/components/estimate-note"
import { QueryChart } from "@/components/query-chart"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { Message, MessageContent, MessageFooter } from "@/components/ui/message"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

/** What Gluco is doing while a tool runs, and once it has finished. */
const TOOL_LABELS: Record<Audience, Record<string, [string, string]>> = {
  patient: {
    get_my_status: ["Checking your latest score", "Checked your latest score"],
    explain_my_change: ["Looking at what changed", "Looked at what changed"],
    get_my_trend: ["Reviewing your recent days", "Reviewed your recent days"],
    query_my_data: [
      "Looking through your readings",
      "Looked through your readings",
    ],
  },
  clinician: {
    list_participants: ["Ranking patients", "Ranked patients"],
    get_participant: ["Retrieving patient summary", "Retrieved patient summary"],
    explain_change: [
      "Analysing change against baseline",
      "Analysed change against baseline",
    ],
    compare_to_cohort: ["Comparing with panel", "Compared with panel"],
    cohort_overview: ["Summarising panel", "Summarised panel"],
    query_data: ["Retrieving readings", "Retrieved readings"],
  },
}

function toolLabel(tool: string, audience: Audience, done: boolean) {
  const labels = TOOL_LABELS[audience][tool]
  if (labels) return labels[done ? 1 : 0]
  return done ? "Looked that up" : "Looking that up"
}

function Part({ part, audience }: { part: ChatPart; audience: Audience }) {
  switch (part.kind) {
    case "text":
      return (
        <Bubble variant="ghost">
          <BubbleContent>
            <Markdown>{part.text}</Markdown>
          </BubbleContent>
        </Bubble>
      )
    case "tool":
      return (
        <Marker>
          <MarkerIcon>
            {part.status === "running" ? <Spinner /> : <CheckIcon />}
          </MarkerIcon>
          <MarkerContent
            className={cn(
              "line-clamp-1 text-xs",
              part.status === "running" && "shimmer"
            )}
          >
            {toolLabel(part.tool, audience, part.status !== "running")}
            {/* Summaries are for clinicians only; patients see just the activity label. */}
            {part.summary && audience === "clinician"
              ? ` · ${part.summary}`
              : ""}
          </MarkerContent>
        </Marker>
      )
    case "chart":
      return (
        <div className="w-full rounded-lg border bg-card p-3">
          <QueryChart
            result={part.chart}
            snapshot
            hideNote
            height={160}
            audience={audience}
          />
        </div>
      )
    case "error":
      return (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertDescription>{part.message}</AlertDescription>
        </Alert>
      )
  }
}

export function ChatMessage({
  message,
  audience,
}: {
  message: ChatMessageType
  audience: Audience
}) {
  if (message.role === "user") {
    const text = message.parts
      .map((p) => (p.kind === "text" ? p.text : ""))
      .join("")
    return (
      <Message align="end">
        <MessageContent>
          <Bubble align="end">
            <BubbleContent className="whitespace-pre-wrap">
              {text}
            </BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    )
  }

  const thinking = message.pending && message.parts.length === 0
  return (
    <Message align="start">
      <MessageContent>
        {thinking ? (
          <Marker>
            <MarkerIcon>
              <Spinner />
            </MarkerIcon>
            <MarkerContent className="shimmer text-xs">
              {audience === "patient" ? "One moment…" : "Thinking…"}
            </MarkerContent>
          </Marker>
        ) : null}
        {message.parts.map((part, index) => (
          <Part
            key={part.kind === "tool" ? part.callId : index}
            part={part}
            audience={audience}
          />
        ))}
        {message.stopped || message.ungrounded?.length ? (
          <MessageFooter className="gap-2">
            {message.stopped ? <span>Stopped</span> : null}
            {message.ungrounded?.length ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="outline">
                    Some numbers couldn&apos;t be checked
                  </Badge>
                </TooltipTrigger>
                <TooltipContent className="max-w-64">
                  {audience === "patient"
                    ? "A few numbers in this answer couldn't be matched to your data. Please double-check them: "
                    : "These figures were not returned by any data query. Verify before relying on them: "}
                  {message.ungrounded.join(", ")}.
                </TooltipContent>
              </Tooltip>
            ) : null}
          </MessageFooter>
        ) : null}
      </MessageContent>
    </Message>
  )
}
