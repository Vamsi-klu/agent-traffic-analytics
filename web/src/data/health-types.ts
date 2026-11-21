// GET /api/health, and whether the IP address AgentCake reads on a server is a CDN's own (agentcake/address_check.py),
// which /api/overview carries too. Part of the /api contract of ./types.ts, which re-exports these types.
import type { Disk, ReplaysStopped } from "./types"
import type { Places } from "./place-types"

/** Of the latest sessions with an IP address (at most 20), how many came from a CDN's published IP ranges; misconfigured
 *  when that is most of them (agentcake/address_check.py): the address read is then the CDN's, not the visitor's, and
 *  sessions are classified as if they had none. All zero and false where no address is read. */
export type AddressCheck = { sessions: number; cdn: number; misconfigured: boolean }

/** Read by `agentcake doctor` and the install check (same fields as AgentCake 0.3.4); the pages don't use it. */
export type Health = {
  ok: boolean
  version: string
  home: string
  site_key: string | null
  sessions: number
  real_sessions: number
  selfcheck_visits: number
  address_check: AddressCheck
  space: {
    used: number; budget: number; pct: number; days_left: number | null; warn: boolean; full: boolean; freed: number; auto_free: boolean
    disk: Disk
    replays_stopped: ReplaysStopped
  }
  /** The update of the lists and, on a server, the city database: monthly or not (lists_auto_update), the last run
   *  (null before the first; at: ISO time), the failed runs in a row and whether that is enough to warn. */
  updates: {
    auto: boolean
    last: { at: string; how: "auto" | "manual"; ok: boolean; error: string | null; parts: { lists?: "updated" | "failed"; places?: "updated" | "current" | "skipped" | "failed" } } | null
    failures: number
    failing: boolean
  }
  /** Where visitors' places come from, the command that downloads the city database, and the database in use (null
   *  without one; only errors when its folder holds one this version can't read). */
  places: Places & {
    update_command: string
    database: { month?: string; months_old?: number; stale?: boolean; built_at?: string; folder?: string; errors?: string[] } | null
  }
}
