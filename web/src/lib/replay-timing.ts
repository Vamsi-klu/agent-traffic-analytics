// Where a replay is, on the session's own clock (S5.4): which chunks the player needs for a moment, where "Jump to
// hand-off" goes, who the cursor belongs to and the page's address at a moment. Plain functions over the API's numbers
// (src/data/types.ts); the player itself (components/cake/use-replay.ts) is a thin layer over rrweb-player.
import type { Actor, Handoff, ReplayEvent, ReplayInfo, Segment } from "@/data/types"

type Chunks = ReplayInfo["chunks"]

/** rrweb's event type for a page's address and window size (rrweb EventType.Meta). */
export const RRWEB_META = 4
/** rrweb's event type for a whole page (rrweb EventType.FullSnapshot): with none, the player has only the pointer and
 *  the clicks to show. */
export const RRWEB_FULL_SNAPSHOT = 2
/** A jump this close to where the player already is counts as "already there", so pressing again moves on. */
const SAME_MOMENT_MS = 500

/** The chunk a moment falls in: the last one that starts at or before it (the first one for a moment before any). */
export function chunkAt(chunks: Chunks, ms: number): number {
  let found = 0
  chunks.forEach((chunk, n) => { if (chunk.start_ms <= ms) found = n })
  return found
}

/** The last chunk the player must have to show a moment and play on from it: the chunk the moment falls in and the
 *  next one, so the next chunk is there before playback reaches it; never the whole replay at once. -1: no chunks. */
export const lastChunkFor = (chunks: Chunks, ms: number) => Math.min(chunks.length - 1, chunkAt(chunks, ms) + 1)

/** Where "Jump to hand-off" starts the player: leadMs before the next hand-off ahead of the playhead, round to the first
 *  one after the last; never before the session's start. null when the session has no hand-off. */
export function handoffJump(handoffs: Handoff[], playheadMs: number, leadMs: number): number | null {
  if (!handoffs.length) return null
  const starts = handoffs.map((h) => Math.max(0, h.at_ms - leadMs))
  return starts.find((start) => start > playheadMs + SAME_MOMENT_MS) ?? starts[0]
}

/** Who acted at a moment, if anyone did (a moment between two segments belongs to no one). */
export const actorAt = (segments: Segment[], ms: number): Actor | undefined =>
  segments.find((s) => s.start_ms <= ms && ms < s.end_ms)?.who

/** A page address and the moment it opened, from one rrweb Meta event. */
export type PageAt = { ms: number; href: string }

/** The pages a run of events opened (their Meta events), on the session's clock. */
export function pagesIn(events: ReplayEvent[], epochMs: number): PageAt[] {
  return events.filter((e) => e.type === RRWEB_META && typeof e.data.href === "string").map((e) => ({ ms: e.timestamp - epochMs, href: e.data.href as string }))
}

/** When a run of events first holds a whole page, on the session's clock; Infinity when it holds none. */
export function firstPageIn(events: ReplayEvent[], epochMs: number): number {
  const page = events.find((e) => e.type === RRWEB_FULL_SNAPSHOT)
  return page ? page.timestamp - epochMs : Infinity
}

/** The address of the page open at a moment: the last page opened at or before it, else `fallback`. */
export function addressAt(pages: PageAt[], ms: number, fallback: string): string {
  let href = fallback
  for (const page of pages) if (page.ms <= ms) href = page.href
  return href
}

/** A moment kept inside the session: 0 … duration. */
export const clampMs = (ms: number, durationMs: number) => Math.min(Math.max(0, ms), durationMs)
