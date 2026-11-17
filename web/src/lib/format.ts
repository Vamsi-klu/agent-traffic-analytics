// Turns the API's raw numbers into what the pages show: times inside a session are milliseconds, sizes are
// bytes (src/data/types.ts). Units, not settings: the scales below never change.
const SECOND_MS = 1000
const MINUTE_S = 60
const HOUR_S = 60 * MINUTE_S
const BINARY = 1024
const SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"]
const MONTH_DAYS = 30
const YEAR_DAYS = 365
const pad2 = (n: number) => String(n).padStart(2, "0")

/** Player clock, in whole seconds rounded down like a player: 96400 → "1:36", 3723000 → "1:02:03". */
export function clock(ms: number): string {
  const s = Math.floor(ms / SECOND_MS)
  const h = Math.floor(s / HOUR_S), m = Math.floor((s % HOUR_S) / MINUTE_S), rest = s % MINUTE_S
  return h ? `${h}:${pad2(m)}:${pad2(rest)}` : `${m}:${pad2(rest)}`
}

/** How long a session lasted: 13000 → "13s", 125000 → "2m 05s", 3720000 → "1h 02m". */
export function duration(ms: number): string {
  const s = Math.floor(ms / SECOND_MS)
  if (s < MINUTE_S) return `${s}s`
  if (s < HOUR_S) return `${Math.floor(s / MINUTE_S)}m ${pad2(s % MINUTE_S)}s`
  return `${Math.floor(s / HOUR_S)}h ${pad2(Math.floor((s % HOUR_S) / MINUTE_S))}m`
}

/** A size in binary units like cake's command line, one decimal unless whole: 3328599654 → "3.1 GB", 2^33 → "8 GB". */
export function bytes(n: number): string {
  let value = n, unit = 0
  while (value >= BINARY && unit < SIZE_UNITS.length - 1) { value /= BINARY; unit++ }
  const shown = unit < 2 ? Math.round(value).toString() : value.toFixed(1).replace(/\.0$/, "")
  return `${shown} ${SIZE_UNITS[unit]}`
}

/** Megabytes (the budget setting) in bytes. */
export const mbToBytes = (mb: number) => mb * BINARY * BINARY

/** A span of days, roughly: 0.5 → "less than a day", 12 → "about 12 days", 120 → "about 4 months". */
export function aboutDays(days: number): string {
  if (days < 1) return "less than a day"
  if (days < 2 * MONTH_DAYS) return `about ${Math.round(days)} days`
  if (days < YEAR_DAYS) return `about ${Math.round(days / MONTH_DAYS)} months`
  return "more than a year"
}

/** What a value reads as when there is none: a number without data, a field the API left empty (DESIGN.md §6). */
export const NO_VALUE = "—"

/** A whole, in percent. */
export const PERCENT = 100

/** Whole percent of a part, 0 when the whole is 0. */
export const percent = (part: number, whole: number) => (whole > 0 ? Math.round((part * PERCENT) / whole) : 0)

/** An address as an address bar or a link label shows it: no scheme. */
export const withoutScheme = (url: string) => url.replace(/^[a-z][a-z0-9+.-]*:\/\//i, "")

/** The website's address from its domain: http for a site on this computer, https for any other. */
export function siteAddress(domain: string) {
  const host = domain.replace(/:\d+$/, "").toLowerCase()
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(host) || host.endsWith(".localhost")
  return `${local ? "http" : "https"}://${domain}/`
}

/** Minutes with one decimal ("2.6"), for active time spent. */
export const minutes = (ms: number) => (ms / (SECOND_MS * MINUTE_S)).toFixed(1)
