// The JSON of GET /api/web (agentcake/api/web.py): visitors and the dashboard's Sources, Devices and Geography tables.
// Part of the /api contract of ./types.ts, which re-exports these types (kept apart so each file stays one job).
import type { DateRange } from "./types"

export type WebQuery = { range?: DateRange }
/** The tables' dimensions, as PostHog's web analytics breaks a table down. */
export type WebDimension =
  | "channel" | "referring_domain" | "utm_source" | "utm_medium" | "utm_campaign"
  | "device_type" | "browser" | "os"
  | "country" | "region" | "city" | "timezone" | "language"
/** One value of a dimension: its Agent and Human sessions, the distinct visitor ids of its sessions, of its Agent and
 *  of its Human ones (null: none has one) and its page views, in all and by Agent and Human. key: what /api/sessions takes (null: the sessions without
 *  a value); value: what the row shows (null: not set; "" for the referring domain: no referrer); country: the country
 *  of a region or a city. */
export type WebRow = {
  key: string | null; value: string | null; country: string | null; agent: number; human: number
  visitors: number | null; agent_visitors: number | null; human_visitors: number | null
  page_views: number; agent_page_views: number; human_page_views: number
}
export type WebTable = { dimension: WebDimension; rows: WebRow[] }[]
/** The sessions of one verdict that began in an interval: how many, their visitor ids (0 without sessions, null when
 *  none has one), page views, average active time (ms; null without a time) and pages per session (null without). */
export type TrendNumbers = { sessions: number; visitors: number | null; page_views: number; active_ms: number | null; pages_per_session: number | null }
/** One agent's Agent sessions in the range, counted as TrendNumbers are (name null: the ones no name fits, Unnamed). */
export type AgentNumbers = TrendNumbers & { name: string | null }
export type TrendInterval = "hour" | "day"
/** Which points the time axis names: every Nth from the first, or each month's first day and the first point. */
export type TrendEvery = number | "month"
/** Average active time (time less the time the page was hidden) and time of a session, ms; null without sessions. */
export type ActiveTime = { active_ms: number; total_ms: number } | null
/** One path: the sessions that viewed it, their visitor ids and their page views of it, in all, Agent and Human. */
export type PathRow = {
  path: string; agent: number; human: number; visitors: number | null; agent_visitors: number | null; human_visitors: number | null
  page_views: number; agent_page_views: number; human_page_views: number
}
export type WebAnalytics = {
  /** Distinct visitors of the range's sessions (visitor ids, merged by the identify hash they were sent with): all of
   *  them, and those with an Agent, a Human or a Bot session (a visitor can be in several); null when none has a
   *  visitor id. without: sessions with no visitor id. */
  visitors: { all: number | null; agent: number | null; human: number | null; bot: number | null; without: number }
  /** Page views (each page load and each new path) of all the range's sessions (bots included) and of each verdict. */
  page_views: { all: number; agent: number; human: number; bot: number }
  /** Active time spent, averaged over all sessions, the Agent, the Human and the Bot ones. */
  active_time: { all: ActiveTime; agent: ActiveTime; human: ActiveTime; bot: ActiveTime }
  /** The Trends chart: each hour (the last 24 hours) or day (7 and 30 days, all time) of the range, the Agent and the
   *  Human sessions that began in it. */
  trends: { interval: TrendInterval; every: TrendEvery; points: { key: string; label: string; agent: TrendNumbers; human: TrendNumbers }[] }
  /** Top agents: the range's Agent sessions (never a bot) by agent name, most sessions first. */
  agents: AgentNumbers[]
  /** The Path table (Human and Agent sessions), most sessions first. */
  paths: PathRow[]
  tables: { sources: WebTable; devices: WebTable; geography: WebTable }
  /** How many rows a table shows before Show all. */
  shown: number
  /** Whether the load balancer gives a session's country, region and city (a server with trust_lb). */
  place: boolean
  /** What the Trends chart's note calls the time zone its days and hours are in: "PST", "UTC", "UTC+05:45". */
  time_zone: string
}
