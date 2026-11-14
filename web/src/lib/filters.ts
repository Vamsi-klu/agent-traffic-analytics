// The filters the dashboard and the session list keep in the URL (like PostHog 1.0's), read with a fallback so an old
// or hand-edited link still opens the page. Values are the API's (src/data/types.ts).
import type { AgentTurns, DateRange, Evidence, Verdict } from "@/data/types"
import { TURNS_ORDER, VERDICT_ORDER } from "./taxonomy"
import { RANGES } from "./words"

export const ALL = "all"
export const ANY_AGENT = "any"
export const DEFAULT_RANGE: DateRange = "7d"
export const RANGE_KEYS = Object.keys(RANGES) as DateRange[]
/** The session list's verdict filter: all, or one verdict (D39's level 1). */
export const VERDICT_FILTERS: (Verdict | typeof ALL)[] = [ALL, ...VERDICT_ORDER]

/** The URL's value when it is one of `choices`, else `fallback`. */
export function pick<T extends string>(value: string | null, choices: readonly T[], fallback: T): T {
  return choices.find((c) => c === value) ?? fallback
}

export const readRange = (params: URLSearchParams) => pick(params.get("range"), RANGE_KEYS, DEFAULT_RANGE)
/** An Agent session's split filter; "all" means either. */
export const readTurns = (params: URLSearchParams) => pick<AgentTurns | typeof ALL>(params.get("turns"), [ALL, ...TURNS_ORDER], ALL)
/** A Human session's evidence filter: "all", or thin (the sessions cake couldn't tell). */
export const readEvidence = (params: URLSearchParams) => pick<Evidence | typeof ALL>(params.get("evidence"), [ALL, "thin"], ALL)
/** "all" means no filter. */
export const choiceQuery = <T extends string>(value: T | typeof ALL) => (value === ALL ? undefined : value)
