"use client"

import { useSyncExternalStore } from "react"

import type { LiveReading } from "@/lib/api/events"

/**
 * The newest live readings from the stream. They change every second, so they
 * live outside React state: only components that read them re-render.
 */
export type LiveSnapshot = {
  /** Newest sensor time across everyone; null without live data. */
  at: string | null
  byPerson: ReadonlyMap<string, LiveReading>
}

const EMPTY: LiveSnapshot = { at: null, byPerson: new Map() }

let snapshot = EMPTY
const listeners = new Set<() => void>()

export function publishLive(at: string | null, readings: LiveReading[]) {
  if (at === snapshot.at && readings.length === snapshot.byPerson.size) return
  snapshot = {
    at,
    byPerson: new Map(readings.map((r) => [r.person_id, r])),
  }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Everyone's live readings. */
export function useLiveReadings(): LiveSnapshot {
  return useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => EMPTY
  )
}

/** One participant's live readings, or undefined when there are none. */
export function useLiveReading(
  personId: string | null | undefined
): LiveReading | undefined {
  return useSyncExternalStore(
    subscribe,
    () => (personId ? snapshot.byPerson.get(personId) : undefined),
    () => undefined
  )
}
