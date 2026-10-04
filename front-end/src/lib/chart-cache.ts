import type { QueryResult } from "@/lib/api/events"

// GET /chat/sessions/{id} returns text only, so the charts an answer drew are
// kept here, per user and thread, keyed by the turn (the index of the user
// message that started it). Only this browser can restore them.

type Turns = Record<string, QueryResult[]>

function storageKey(userId: string, sessionId: string) {
  return `gluco:charts:${userId}:${sessionId}`
}

export function readCharts(userId: string, sessionId: string): Turns | null {
  try {
    const raw = window.localStorage.getItem(storageKey(userId, sessionId))
    return raw ? (JSON.parse(raw) as Turns) : null
  } catch {
    return null
  }
}

export function saveChart(
  userId: string,
  sessionId: string,
  turn: number,
  chart: QueryResult
) {
  try {
    const turns = readCharts(userId, sessionId) ?? {}
    turns[turn] = [...(turns[turn] ?? []), chart]
    window.localStorage.setItem(
      storageKey(userId, sessionId),
      JSON.stringify(turns)
    )
  } catch {
    // Quota or private mode: the chart still shows now, it just won't come back.
  }
}
