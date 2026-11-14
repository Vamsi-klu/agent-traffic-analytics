// What a recorded sample replay is, shared by the recorder (scripts/replay-fixtures.mjs) and its test
// (scripts/replay-samples.test.mjs): rrweb events cut into chunks the way cake cuts them, the server half's rows from
// cake's srv table, and what must never be in a sample.
import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const repo = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..")
const readJson = (file) => JSON.parse(readFileSync(file, "utf8"))

/** cake's chunk length (agentcake/data/storage.json): a chunk holds the events of one window of the events' clock. */
export const CHUNK_MS = readJson(path.join(repo, "agentcake", "data", "storage.json")).chunk_ms
/** The local page's default port (agentcake/defaults.json): the address samples show. */
export const DEFAULT_PORT = readJson(path.join(repo, "agentcake", "defaults.json")).port.default
export const SITE_KEY_PLACEHOLDER = "<your-site-key>"
/** rrweb's event types for a page's address and window size, and for the page's full snapshot. */
export const RRWEB = { meta: 4, fullSnapshot: 2 }

// Card numbers as pages show and people type them, in groups (an event's timestamp is a 13-digit run, so runs alone
// can't tell), and the shop's own sample number.
const NEVER = [/\b\d{4}([ -])\d{4}\1\d{4}\1\d{1,4}\b/, /\b4242\b/]

/** The first thing in `text` that must never be in a sample: one of `banned` (what was typed, scratch paths, keys) or a
 *  card number; null when there is none. */
export function forbidden(text, banned) {
  return banned.find((b) => b && text.includes(b)) ?? NEVER.map((re) => text.match(re)?.[0]).find(Boolean) ?? null
}

/** Events (oldest first) in cake's chunks: one per window of CHUNK_MS on the events' own clock (streams.append), with
 *  the session moments of its first and last event (t0: the session's ms 0, epoch ms). */
export function chunksOf(events, t0) {
  const windows = new Map()
  for (const event of events) {
    const start = event.timestamp - (event.timestamp % CHUNK_MS)
    if (!windows.has(start)) windows.set(start, [])
    windows.get(start).push(event)
  }
  return [...windows.values()].map((list, chunk) => ({ chunk, start_ms: list[0].timestamp - t0, end_ms: list.at(-1).timestamp - t0, events: list }))
}

/** How many page views [ts, text, page view] rows hold; throws when two overlap in time (a walk is one tab, one page at
 *  a time: a page's events all come before the next page's first event). */
export function pageViews(rows, label) {
  const spans = new Map()
  for (const [ts, , page] of rows) {
    const span = spans.get(page) ?? [ts, ts]
    spans.set(page, [Math.min(span[0], ts), Math.max(span[1], ts)])
  }
  const ordered = [...spans.values()].sort((a, b) => a[0] - b[0])
  ordered.forEach((span, i) => { if (i && span[0] <= ordered[i - 1][1]) throw new Error(`${label}: two page views overlap in time`) })
  return ordered.length
}

/** null stays null (cake can't tell), else whether it matched: as agentcake/api/server_half.py's _same. */
const same = (match) => (match === null ? null : Boolean(match))

/** One server-half row of a sample from an srv row [page_ms, path, token JSON, net_match, ua_match, lang_match, reuses]
 *  (agentcake/edge_token.py: its matches and reuses), as agentcake/api/server_half.py answers it. */
export function serverPage([pageMs, pagePath, body, netMatch, uaMatch, langMatch, reuses], t0) {
  const token = JSON.parse(body), sf = token.sf ?? {}, sg = token.sg ?? {}
  return {
    at_ms: Math.max(0, pageMs - t0),
    path: pagePath,
    fetch: { site: sf.s ?? null, mode: sf.m ?? null, dest: sf.d ?? null, user: sf.u ?? null },
    signature: sg.s ? { agent: sg.a ?? null, verified: false } : null, // verifying is the verify layer's job
    same_network: same(netMatch),
    same_user_agent: same(uaMatch),
    same_language: same(langMatch),
    reuses: reuses ?? 0,
  }
}
