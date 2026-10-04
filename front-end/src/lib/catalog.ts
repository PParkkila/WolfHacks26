"use client"

import { useMemo } from "react"

import type { Schemas } from "@/lib/api/client"
import { useCatalog } from "@/lib/api/queries"

export type MetricInfo = Schemas["MetricInfo"]

// The model's outputs. Every other catalog metric is measured by the wearable:
// 24-hour summaries ("sensors") or seconds-old readings ("live").
export const GLUCO_SCORE = "gluco_score"
export const GLUCO_CHANGE = "gluco_change_24h"

/** Labels, units and descriptions for every metric, from GET /catalog. */
export function useMetrics() {
  const catalog = useCatalog()
  return useMemo(() => {
    const list = catalog.data?.metrics ?? []
    const byName = new Map(list.map((m) => [m.name, m]))
    return {
      ready: catalog.isSuccess,
      list,
      sensors: list.filter(
        (m) => m.name !== GLUCO_SCORE && m.name !== GLUCO_CHANGE && !m.live
      ),
      live: list.filter((m) => m.live),
      get: (name: string): MetricInfo | undefined => byName.get(name),
      anyLive: (names: string[]) => names.some((n) => byName.get(n)?.live),
      label: (name: string) => byName.get(name)?.label ?? name,
    }
  }, [catalog.data, catalog.isSuccess])
}

function decimals(metric: string, value: number): number {
  if (metric === GLUCO_SCORE) return 0
  if (metric === GLUCO_CHANGE) return 1
  const size = Math.abs(value)
  if (size >= 100) return 0
  if (size >= 10) return 1
  if (size >= 0.1) return 2
  return 3
}

/** A value rounded for display, as a number (for charts and tooltips). */
export function roundValue(metric: string, value: number): number {
  const factor = 10 ** decimals(metric, value)
  return Math.round(value * factor) / factor
}

export function formatValue(
  metric: string,
  value: number | null | undefined,
  { signed = false }: { signed?: boolean } = {}
): string {
  if (value == null || Number.isNaN(value)) return "—"
  const places = decimals(metric, value)
  const text = Math.abs(value).toFixed(places)
  if (Number(text) === 0) return (0).toFixed(places)
  const sign = value < 0 ? "−" : signed ? "+" : ""
  return `${sign}${text}`
}

/**
 * The unit to print after a value: the catalog unit without its parenthetical,
 * and nothing when that isn't a short unit ("correlation (-1 to 1)").
 */
export function shortUnit(unit: string | undefined): string {
  if (!unit) return ""
  const bare = unit.split(" (")[0]
  return bare.length <= 6 ? bare : ""
}

export function formatWithUnit(
  metric: MetricInfo | undefined,
  name: string,
  value: number | null | undefined,
  options?: { signed?: boolean }
): string {
  const text = formatValue(name, value, options)
  const unit = shortUnit(metric?.unit)
  return value == null || !unit ? text : `${text} ${unit}`
}
