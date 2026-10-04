"use client"

import { useQueryClient } from "@tanstack/react-query"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import { api, ApiError, unwrap } from "@/lib/api/client"
import type { ChatEvent, QueryResult } from "@/lib/api/events"
import { keys } from "@/lib/api/queries"
import { streamSSE } from "@/lib/api/sse"
import { readCharts, saveChart } from "@/lib/chart-cache"
import type { Principal } from "@/lib/session"

export type ChatPart =
  | { kind: "text"; text: string }
  | {
      kind: "tool"
      callId: string
      tool: string
      status: "running" | "done"
      summary?: string
    }
  | { kind: "chart"; callId?: string; chart: QueryResult }
  | { kind: "error"; message: string }

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  parts: ChatPart[]
  /** Still streaming. */
  pending?: boolean
  stopped?: boolean
  /** Numbers in the answer that no tool returned (from the `done` event). */
  ungrounded?: string[]
}

type ChatContextValue = {
  sessionId: string
  messages: ChatMessage[]
  streaming: boolean
  loadingThread: boolean
  /** A reopened thread whose charts this browser didn't keep. */
  chartsMissing: boolean
  send: (text: string) => void
  stop: () => void
  newChat: () => void
  openThread: (sessionId: string) => Promise<void>
}

const ChatContext = createContext<ChatContextValue | null>(null)

function newId() {
  return crypto.randomUUID()
}

/** Apply one Contract B event to the assistant message being streamed. */
function reduce(message: ChatMessage, event: ChatEvent): ChatMessage {
  const parts = [...message.parts]
  switch (event.type) {
    case "token": {
      const last = parts.at(-1)
      if (last?.kind === "text")
        parts[parts.length - 1] = { ...last, text: last.text + event.text }
      else parts.push({ kind: "text", text: event.text })
      return { ...message, parts }
    }
    case "tool_start":
      parts.push({
        kind: "tool",
        callId: event.call_id,
        tool: event.tool,
        status: "running",
      })
      return { ...message, parts }
    case "tool_end":
      return {
        ...message,
        parts: parts.map((part) =>
          part.kind === "tool" && part.callId === event.call_id
            ? { ...part, status: "done", summary: event.summary }
            : part
        ),
      }
    case "data": {
      // Place the chart right after the tool call that produced it.
      const at = parts.findIndex(
        (p) => p.kind === "tool" && p.callId === event.call_id
      )
      const chart: ChatPart = {
        kind: "chart",
        callId: event.call_id,
        chart: event.chart,
      }
      if (at === -1) parts.push(chart)
      else parts.splice(at + 1, 0, chart)
      return { ...message, parts }
    }
    case "error":
      parts.push({ kind: "error", message: event.message })
      return { ...message, parts }
    case "done":
      return event.ungrounded_numbers?.length
        ? { ...message, ungrounded: event.ungrounded_numbers }
        : message
  }
}

export function ChatProvider({
  principal,
  children,
}: {
  principal: Principal
  children: React.ReactNode
}) {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState(newId)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [loadingThread, setLoadingThread] = useState(false)
  const [chartsMissing, setChartsMissing] = useState(false)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const stop = useCallback(() => controller.current?.abort(), [])

  const send = useCallback(
    (text: string) => {
      const message = text.trim()
      if (!message || controller.current) return

      const abort = new AbortController()
      controller.current = abort
      const turn = messages.filter((m) => m.role === "user").length
      const assistantId = newId()
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "user", parts: [{ kind: "text", text: message }] },
        { id: assistantId, role: "assistant", parts: [], pending: true },
      ])
      setStreaming(true)

      const update = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? fn(m) : m))
        )

      void streamSSE(
        "/chat",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message }),
          signal: abort.signal,
        },
        (data) => {
          const event = data as ChatEvent
          if (event.type === "data") {
            saveChart(principal.user_id, sessionId, turn, event.chart)
          }
          update((m) => reduce(m, event))
        }
      )
        .catch((error: unknown) => {
          if (abort.signal.aborted) {
            update((m) => ({ ...m, stopped: true }))
            return
          }
          const text =
            error instanceof ApiError
              ? error.message
              : "The assistant couldn't be reached."
          update((m) => ({
            ...m,
            parts: [...m.parts, { kind: "error", message: text }],
          }))
        })
        .finally(() => {
          update((m) => ({ ...m, pending: false }))
          controller.current = null
          setStreaming(false)
          void queryClient.invalidateQueries({ queryKey: keys.threads })
        })
    },
    [messages, principal.user_id, queryClient, sessionId]
  )

  const newChat = useCallback(() => {
    controller.current?.abort()
    setSessionId(newId())
    setMessages([])
    setChartsMissing(false)
  }, [])

  const openThread = useCallback(
    async (id: string) => {
      controller.current?.abort()
      setSessionId(id)
      setMessages([])
      setChartsMissing(false)
      setLoadingThread(true)
      try {
        const history = await unwrap(
          api.GET("/chat/sessions/{session_id}", {
            params: { path: { session_id: id } },
          })
        )
        const charts = readCharts(principal.user_id, id)
        const restored: ChatMessage[] = []
        let turn = -1
        history.forEach((item, index) => {
          const role = item.role === "user" ? "user" : "assistant"
          if (role === "user") turn += 1
          const parts: ChatPart[] = [{ kind: "text", text: item.text }]
          // A turn's charts go after its last assistant message.
          const endsTurn =
            role === "assistant" && history[index + 1]?.role !== "assistant"
          if (endsTurn && turn >= 0) {
            for (const chart of charts?.[turn] ?? [])
              parts.push({ kind: "chart", chart })
          }
          restored.push({ id: newId(), role, parts })
        })
        setMessages(restored)
        setChartsMissing(
          !charts && restored.some((m) => m.role === "assistant")
        )
      } catch (error) {
        setMessages([
          {
            id: newId(),
            role: "assistant",
            parts: [
              {
                kind: "error",
                message:
                  error instanceof Error
                    ? error.message
                    : "Couldn't open that conversation.",
              },
            ],
          },
        ])
      } finally {
        setLoadingThread(false)
      }
    },
    [principal.user_id]
  )

  const value = useMemo(
    () => ({
      sessionId,
      messages,
      streaming,
      loadingThread,
      chartsMissing,
      send,
      stop,
      newChat,
      openThread,
    }),
    [
      sessionId,
      messages,
      streaming,
      loadingThread,
      chartsMissing,
      send,
      stop,
      newChat,
      openThread,
    ]
  )
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat(): ChatContextValue {
  const value = useContext(ChatContext)
  if (!value) throw new Error("useChat must be used inside <ChatProvider>")
  return value
}
