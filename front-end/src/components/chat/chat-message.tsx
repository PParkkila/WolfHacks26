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

/** "get_my_status" -> "Get my status" */
function humanize(tool: string) {
  const words = tool.replace(/[_-]+/g, " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
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
            {humanize(part.tool)}
            {/* Tool summaries are technical; patients see only what was looked up. */}
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
            <MarkerContent className="shimmer text-xs">Thinking…</MarkerContent>
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
                  These figures in the answer didn&apos;t come from any data
                  lookup: {message.ungrounded.join(", ")}. Treat them with care.
                </TooltipContent>
              </Tooltip>
            ) : null}
          </MessageFooter>
        ) : null}
      </MessageContent>
    </Message>
  )
}
