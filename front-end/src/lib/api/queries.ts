"use client"

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import { api, unwrap, type Schemas } from "@/lib/api/client"

export type QuerySpec = Schemas["QuerySpec"]
export type WidgetSpec = Schemas["WidgetSpec"]
export type SortOrder = "asc" | "desc"

/**
 * Query keys. Everything that depends on the replay clock lives under `data`, so
 * one invalidation refreshes every view when the clock moves.
 */
export const keys = {
  data: ["data"] as const,
  catalog: ["catalog"] as const,
  personas: ["personas"] as const,
  cohort: ["data", "cohort"] as const,
  participants: (sortBy: string, order: SortOrder) =>
    ["data", "participants", sortBy, order] as const,
  participant: (id: string) => ["data", "participant", id] as const,
  explain: (id: string, hours: number) =>
    ["data", "explain", id, hours] as const,
  query: (spec: QuerySpec) => ["data", "query", spec] as const,
  // The pin list is not under `data`: it only changes when the user pins.
  pins: ["pins"] as const,
  widget: (id: string) => ["data", "widget", id] as const,
  chat: ["chat"] as const,
  threads: ["chat", "threads"] as const,
}

export function usePersonas(enabled = true) {
  return useQuery({
    queryKey: keys.personas,
    queryFn: () => unwrap(api.GET("/personas")),
    staleTime: 60_000,
    enabled,
  })
}

/** Metric labels, units and descriptions. Static for a session. */
export function useCatalog() {
  return useQuery({
    queryKey: keys.catalog,
    queryFn: () => unwrap(api.GET("/catalog")),
    staleTime: Infinity,
  })
}

/** Clinicians only: the back-end answers 403 for patients. */
export function useCohort() {
  return useQuery({
    queryKey: keys.cohort,
    queryFn: () => unwrap(api.GET("/cohort")),
    placeholderData: keepPreviousData,
  })
}

export function useParticipants(sortBy: string, order: SortOrder) {
  return useQuery({
    queryKey: keys.participants(sortBy, order),
    queryFn: () =>
      unwrap(
        api.GET("/participants", {
          params: { query: { sort_by: sortBy, order } },
        })
      ),
    placeholderData: keepPreviousData,
  })
}

export function useParticipant(id: string | null | undefined) {
  return useQuery({
    queryKey: keys.participant(id ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/participants/{person_id}", {
          params: { path: { person_id: id! } },
        })
      ),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })
}

export function useExplain(id: string | null | undefined, hours: number) {
  return useQuery({
    queryKey: keys.explain(id ?? "", hours),
    queryFn: () =>
      unwrap(
        api.GET("/participants/{person_id}/explain", {
          params: { path: { person_id: id! }, query: { hours } },
        })
      ),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })
}

/** The generic POST /query behind most charts. */
export function useSeries(spec: QuerySpec, enabled = true) {
  return useQuery({
    queryKey: keys.query(spec),
    queryFn: () => unwrap(api.POST("/query", { body: spec })),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useThreads() {
  return useQuery({
    queryKey: keys.threads,
    queryFn: () => unwrap(api.GET("/chat/sessions")),
  })
}

export function usePinnedWidgets() {
  return useQuery({
    queryKey: keys.pins,
    queryFn: () => unwrap(api.GET("/widgets")),
  })
}

/** A pinned widget rebuilt on the server (query + compliance check). */
export function useWidgetData(id: string) {
  return useQuery({
    queryKey: keys.widget(id),
    queryFn: () =>
      unwrap(
        api.GET("/widgets/{widget_id}/data", {
          params: { path: { widget_id: id } },
        })
      ),
    placeholderData: keepPreviousData,
  })
}

export function usePinWidget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (spec: WidgetSpec) =>
      unwrap(api.POST("/widgets", { body: spec })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.pins }),
  })
}

export function useUnpinWidget() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/widgets/{widget_id}", {
          params: { path: { widget_id: id } },
        })
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.pins }),
  })
}
