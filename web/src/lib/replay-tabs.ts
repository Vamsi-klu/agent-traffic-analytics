// Which tab a session's replay shows (DESIGN.md §6.4): a session of more than one tab plays one tab's replay at
// a time, as PostHog's player plays one window of a recording. Following the visitor, it shows the tab the visitor is
// active in at each moment (the API's follow stretches: PostHog's segmenter); with a tab picked, that tab's own replay
// throughout (its parts in turn, when it went quiet for 30 minutes and went on). Plain functions over the API's answer
// (src/data/types.ts); use-replay.ts moves the player from one tab's replay to another's.
import type { ReplayInfo, Segment, SessionDetail } from "@/data/types"

/** What the replay shows: the tab the visitor is active in, or the tab with this number. */
export type ReplayView = "follow" | number

/** One replay the player can play: a session's own (a session of one tab), or one tab's. */
export type ReplaySource = {
  /** The tab's id (…/replay?tab=); null for a session of one tab. */
  id: string | null
  /** Its tab's number; null for a session of one tab. */
  tab: number | null
  replay: Pick<ReplayInfo, "start_ms" | "start_url" | "epoch_ms" | "chunks" | "missing">
  /** Who acted when in it (the cursor's name), and its agent's name. */
  segments: Segment[]
  agent: string | null
  /** When its recording starts and ends, on the session's clock. */
  start_ms: number
  end_ms: number
}

/** A replay is there to play unless it was deleted or never had anything in it ("dropped" still plays what is left). */
export const playable = (replay: Pick<ReplayInfo, "chunks" | "missing">) =>
  replay.chunks.length > 0 && replay.missing !== "freed" && replay.missing !== "none"

/** The replays a session's page can play: its own, or each tab's (with the session's clock). */
export function sourcesOf(d: SessionDetail): ReplaySource[] {
  if (!d.tabs) {
    return [{ id: null, tab: null, replay: d.replay, segments: d.timeline.segments, agent: d.session.agent, start_ms: 0, end_ms: d.timeline.duration_ms }]
  }
  return d.tabs.map((t) => ({
    id: t.id, tab: t.tab, replay: { ...t.replay, epoch_ms: d.replay.epoch_ms }, segments: t.segments, agent: t.agent, start_ms: t.start_ms, end_ms: t.end_ms,
  }))
}

/** The session's tab numbers, Tab 1 first; none for a session of one tab. */
export const tabNumbers = (sources: ReplaySource[]) => [...new Set(sources.flatMap((s) => (s.tab === null ? [] : [s.tab])))]

/** The view the page opens with: the tab an address named (an address from before sessions spanned tabs), else
 *  following the visitor. */
export function openingView(d: SessionDetail, sources: ReplaySource[]): ReplayView {
  const named = d.named_tab === undefined ? undefined : sources.find((s) => s.id === d.named_tab)
  return named?.tab ?? "follow"
}

/** Where the player opens: the replay's start, or with a tab picked, where that tab's replay starts: the part an
 *  address named, when it is that tab's, else its first. */
export function openingMs(d: SessionDetail, sources: ReplaySource[], view: ReplayView): number {
  if (view === "follow") return d.replay.start_ms
  const part = sources.find((s) => s.tab === view && s.id === d.named_tab) ?? sources.find((s) => s.tab === view)
  return part?.replay.start_ms ?? d.replay.start_ms
}

/** The source to show at a moment (an index of sources). Following: the tab the follow stretch there names, or, when its
 *  replay can't be played, the one shown now (or the first that can be). A tab picked: its part whose recording spans the
 *  moment, else its last part to start before it, else its first. */
export function sourceAt(d: SessionDetail, sources: ReplaySource[], view: ReplayView, ms: number, shown: number): number {
  if (sources.length < 2) return 0
  if (view !== "follow") {
    const parts = sources.flatMap((s, i) => (s.tab === view ? [i] : []))
    return parts.find((i) => sources[i].start_ms <= ms && ms <= sources[i].end_ms)
      ?? [...parts].reverse().find((i) => sources[i].start_ms <= ms) ?? parts[0] ?? shown
  }
  const stretches = d.follow ?? []
  const stretch = stretches.find((s) => s.start_ms <= ms && ms < s.end_ms) ?? (ms < (stretches[0]?.start_ms ?? 0) ? stretches[0] : stretches[stretches.length - 1])
  const named = stretch ? sources.findIndex((s) => s.id === stretch.tab) : -1
  if (named >= 0 && playable(sources[named].replay)) return named
  if (playable(sources[shown].replay)) return shown
  const first = sources.findIndex((s) => playable(s.replay))
  return first >= 0 ? first : Math.max(0, named)
}

/** Where playback goes on once the shown replay ran out at ms: following, the next stretch of another tab that can be
 *  played; a tab picked, its next part that can be. null: the session's replay is over. */
export function nextAfter(d: SessionDetail, sources: ReplaySource[], view: ReplayView, shown: number, ms: number): { index: number; ms: number } | null {
  if (sources.length < 2) return null
  if (view !== "follow") {
    const next = sources.findIndex((s, i) => i !== shown && s.tab === view && s.start_ms > ms && playable(s.replay))
    return next >= 0 ? { index: next, ms: sources[next].start_ms } : null
  }
  for (const stretch of d.follow ?? []) {
    const index = sources.findIndex((s) => s.id === stretch.tab)
    if (stretch.end_ms > ms && index >= 0 && index !== shown && playable(sources[index].replay)) return { index, ms: Math.max(ms, stretch.start_ms) }
  }
  return null
}
