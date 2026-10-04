// Payloads of the two SSE endpoints. OpenAPI doesn't describe event streams, so
// these are written by hand from back-end/README.md, reusing the generated
// schemas wherever the payload embeds one.
import type { Schemas } from "@/lib/api/client"

export type QueryResult = Schemas["QueryResult"]
export type ClockState = Schemas["ClockState"]

/** GET /stream */
export type TickEvent = {
  type: "tick"
  clock: ClockState
  /** True after a backwards seek: re-run queries instead of appending. */
  reset: boolean
  new_windows: unknown[]
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
  | { type: "data"; call_id: string; tool: string; chart: QueryResult }
  | { type: "error"; message: string; recoverable: boolean }
  | { type: "done"; session_id: string; ungrounded_numbers?: string[] }
