// Every time on screen is replay time (`as_of`, window ends), shown in UTC so
// days line up with the back-end's UTC day buckets. Nothing here reads the
// wall clock.

const parts = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

function pieces(iso: string) {
  const out: Record<string, string> = {}
  for (const part of parts.formatToParts(new Date(iso)))
    out[part.type] = part.value
  return out
}

/** "Tue 29 Sep, 14:00" */
export function formatReplayTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const p = pieces(iso)
  return `${p.weekday} ${p.day} ${p.month}, ${p.hour}:${p.minute}`
}

/** "Tue 29 Sep" */
export function formatReplayDay(iso: string | null | undefined): string {
  if (!iso) return "—"
  const p = pieces(iso)
  return `${p.weekday} ${p.day} ${p.month}`
}

/** Axis tick for a point time, by the query's bucket. */
export function formatTick(iso: string, bucket: string): string {
  const p = pieces(iso)
  if (bucket === "day") return `${p.weekday} ${p.day}`
  return `${p.weekday} ${p.hour}:${p.minute}`
}

/** "3 h before" style distance between two replay times. */
export function formatGap(
  fromIso: string,
  toIso: string | null | undefined
): string {
  if (!toIso) return ""
  const hours = Math.round(
    (Date.parse(toIso) - Date.parse(fromIso)) / 3_600_000
  )
  if (hours <= 0) return "latest"
  if (hours < 48) return `${hours} h earlier`
  return `${Math.round(hours / 24)} days earlier`
}

/** 1 -> "1st", 22 -> "22nd", 13 -> "13th". */
export function ordinal(n: number): string {
  const value = Math.round(n)
  const mod100 = value % 100
  if (mod100 >= 11 && mod100 <= 13) return `${value}th`
  const suffix = { 1: "st", 2: "nd", 3: "rd" }[value % 10] ?? "th"
  return `${value}${suffix}`
}
