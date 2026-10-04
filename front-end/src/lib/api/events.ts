// Payloads of the two SSE endpoints. OpenAPI doesn't describe event streams, so
// these are written by hand from back-end/README.md, reusing the generated
// schemas wherever the payload embeds one.
import type { Schemas } from "@/lib/api/client"

export type QueryResult = Schemas["QueryResult"]
export type ClockState = Schemas["ClockState"]
export type WidgetSpec = Schemas["WidgetSpec"]
export type WidgetStep = Schemas["WidgetStep"]

/** A widget built in chat: the spec a pin stores, plus how it was built. */
export type ChatWidget = WidgetSpec & { steps: WidgetStep[] }

/** One participant's newest wearable readings, refreshed every second. */
export type LiveReading = {
  person_id: string
  sensor_time: string
  /** End of the newest analytics window, so a change means new analytics. */
  analytics_window_end: string | null
  /** Keyed by the catalog's live metrics; null when the device lacks a sensor. */
  values: Record<string, number | null>
}

/** GET /stream */
export type TickEvent = {
  type: "tick"
  clock: ClockState
  /** True after a backwards seek: re-run queries instead of appending. */
  reset: boolean
  new_windows: unknown[]
  /** Newest sensor time across `live`; null without live data. */
  live_at: string | null
  /** Everyone visible's live readings (empty while the replay is behind). */
  live: LiveReading[]
}

/** POST /chat */
export type ChatEvent =
  | { type: "token"; text: string }
  | {
      type: "tool_start"
      call_id: string
      tool: string
      args: Record<string, unknown>
    }
  | {
      type: "tool_end"
      call_id: string
      tool: string
      summary: string
      rows: number
    }
  | {
      type: "data"
      call_id: string
      tool: string
      chart: QueryResult
      /** Set when the chart is a widget the agent built (build_widget). */
      widget?: ChatWidget
    }
  | { type: "error"; message: string; recoverable: boolean }
  | { type: "done"; session_id: string; ungrounded_numbers?: string[] }
