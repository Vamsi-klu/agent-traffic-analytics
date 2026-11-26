// The replay of one session for React: a ReplayEngine (./replay-engine.ts) on the element `mount` is given, and
// what the stage, the controls and the timeline show. The page passes how to fetch a chunk (only pages call the API)
// and the cursor's label for each actor. A session of more than one tab plays one tab's replay at a time
// (./replay-tabs.ts picks which): when the playhead reaches another tab's stretch, or the shown replay runs out while
// the session goes on, or the owner picks another view, the player opens that tab's replay at the same moment of the
// session's clock, playing on if it was playing; the chunks already read are kept, so going back costs no request.
import { useEffect, useMemo, useRef, useState } from "react"
import type { Actor, ReplayChunk, ReplayMissing, Segment, SessionDetail } from "@/data/types"
import { asApiError } from "@/data/api"
import { ReplayEngine, SPEEDS } from "./replay-engine"
import { nextAfter, openingMs, openingView, playable, sourceAt, sourcesOf, tabNumbers, type ReplayView } from "./replay-tabs"
import { handoffJump } from "./replay-timing"

export { SPEEDS }
export type { ReplayView }

/** loading: the player or its first chunks are on their way · ready · failed: they didn't come · missing: no replay. */
export type ReplayStatus = "loading" | "ready" | "failed" | "missing"

/** A session of more than one tab: its tab numbers, what the replay shows, the tab on the stage with who acted when
 *  in it and its agent's name, and how to pick. */
export type ReplayTabs = {
  numbers: number[]; view: ReplayView; shown: number; segments: Segment[]; agent: string | null; setView(view: ReplayView): void
}

export type ReplayState = {
  status: ReplayStatus
  /** Why there is no replay or only part of one (from the API), else null. */
  missing: ReplayMissing | null
  /** What went wrong, when status is failed. */
  error: string | null
  /** The playhead, on the session's clock. */
  timeMs: number
  playing: boolean
  /** Playing, but the next chunk hasn't arrived yet. */
  waiting: boolean
  /** Ready, but no page was recorded up to the playhead: the stage shows only the pointer and the clicks. */
  noPage: boolean
  speed: number
  /** The address of the page at the playhead. */
  address: string
  /** The player's element: the stage gives it to the engine. */
  mount: (element: HTMLDivElement | null) => void
  play(): void
  pause(): void
  seek(ms: number): void
  setSpeed(speed: number): void
  /** Moves the replay to a moment and plays from there (a page's row in the pages section, Jump to hand-off). */
  jumpTo(ms: number): void
  /** Where "Jump to hand-off" goes from here; null when the session has no hand-off. */
  nextHandoff: number | null
  jumpToHandoff(): void
  retry(): void
  /** Set only for a session of more than one tab. */
  tabs?: ReplayTabs
}

/** fetchChunk: chunk n of the replay (tab: the tab's id, in a session of more than one); labels: the cursor's label for
 *  each actor when the agent acting is the one named. */
export function useReplay(d: SessionDetail, fetchChunk: (n: number, signal: AbortSignal, tab?: string) => Promise<ReplayChunk>,
  labels: (agent: string | null) => Record<Actor, string>): ReplayState {
  const sources = useMemo(() => sourcesOf(d), [d])
  const [element, mount] = useState<HTMLDivElement | null>(null)
  const [view, setViewState] = useState<ReplayView>(() => openingView(d, sources))
  const [shown, setShown] = useState(() => sourceAt(d, sources, view, openingMs(d, sources, view), 0))
  const source = sources[shown]
  const canPlay = playable(source.replay)
  const [status, setStatus] = useState<ReplayStatus>(canPlay ? "loading" : "missing")
  const [error, setError] = useState<string | null>(null)
  const [timeMs, setTimeMs] = useState(() => openingMs(d, sources, view))
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const [paged, setPaged] = useState(true)
  const [speed, setSpeedState] = useState(SPEEDS[0])
  const [address, setAddress] = useState(source.replay.start_url)
  const [attempt, setAttempt] = useState(0)
  const engine = useRef<ReplayEngine | null>(null)
  const start = useRef({ ms: openingMs(d, sources, view), play: false }) // where the next engine starts
  const now = useRef({ view, shown, timeMs, playing, speed, status, ended: false })
  now.current = { ...now.current, view, shown, timeMs, playing, speed, status }
  const queued = useRef<{ ms: number; play: boolean } | null>(null) // a move asked while a tab's replay was loading
  const chunks = useRef(new Map<string, Promise<ReplayChunk>>()) // the tabs' chunks read so far (several tabs only)
  const fetches = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetches.current = controller
    chunks.current = new Map()
    return () => controller.abort()
  }, [d])

  /** Shows another source (never the one shown) from a moment, playing on or not: an engine for it starts there. */
  const switchTo = (index: number, ms: number, play: boolean) => {
    start.current = { ms, play }
    now.current.ended = false
    setShown(index)
    setTimeMs(ms)
    setStatus(playable(sources[index].replay) ? "loading" : "missing")
  }
  const ended = (ms: number) => {
    const next = nextAfter(d, sources, now.current.view, now.current.shown, ms)
    if (next) switchTo(next.index, next.ms, true)
    else now.current.ended = true
  }
  /** The chunk for an engine: a session of one tab reads it with the engine's own request, as it always did; several
   *  tabs keep what they read, so a tab shown again reads nothing twice. */
  const chunkOf = (n: number, signal: AbortSignal) => {
    if (source.id === null) return fetchChunk(n, signal)
    const key = `${source.id}:${n}`
    let found = chunks.current.get(key)
    if (!found) {
      found = fetchChunk(n, fetches.current?.signal ?? signal, source.id)
      found.catch(() => chunks.current.delete(key))
      chunks.current.set(key, found)
    }
    return found
  }

  // fetchChunk and labels are new functions and objects on every render; the session, the source shown and the attempt
  // say when the player must start again. A session of one tab starts at its replay's start, paused, at the first
  // speed, every time; a tab taken over goes on from the moment and at the speed the player was at.
  useEffect(() => {
    if (!element || !canPlay) return
    const controller = new AbortController()
    const fail = (e: unknown) => { if (!controller.signal.aborted) { setError(asApiError(e).message); setStatus("failed"); setPlaying(false) } }
    const single = source.id === null
    const current = new ReplayEngine({
      el: element, replay: source.replay, durationMs: d.timeline.duration_ms, segments: source.segments, labels: labels(source.agent),
      fetchChunk: (n) => chunkOf(n, controller.signal), ...(single ? {} : { startMs: start.current.ms, autoplay: start.current.play }),
      on: { time: setTimeMs, playing: setPlaying, waiting: setWaiting, address: setAddress, page: setPaged, failed: fail, ended },
    })
    engine.current = current
    setStatus("loading")
    setPaged(true)
    if (single) setSpeedState(SPEEDS[0])
    current.start().then(() => {
      if (controller.signal.aborted) return
      if (!single) current.setSpeed(now.current.speed)
      setStatus("ready")
      const move = queued.current
      queued.current = null
      if (move) void current.seek(move.ms, move.play)
    }, fail)
    const observer = new ResizeObserver(() => current.resize())
    observer.observe(element)
    return () => {
      controller.abort()
      observer.disconnect()
      current.destroy()
      engine.current = null
    }
  }, [element, d, canPlay, attempt, shown])

  // following the visitor, the playhead reaching another tab's stretch shows that tab
  useEffect(() => {
    if (sources.length < 2 || status !== "ready") return
    const wanted = sourceAt(d, sources, view, timeMs, shown)
    if (wanted !== shown) switchTo(wanted, timeMs, playing)
  }, [timeMs, view, status])

  const pick = (ms: number) => sourceAt(d, sources, now.current.view, ms, now.current.shown)
  /** Moves a session of several tabs to a moment: another tab's replay when that tab is shown then; within the tab shown,
   *  at once, or as soon as its replay has loaded. */
  const seekTo = (ms: number, play: boolean) => {
    const wanted = pick(ms)
    now.current.ended = false
    if (wanted !== now.current.shown) {
      queued.current = null
      switchTo(wanted, ms, play)
    } else if (now.current.status === "loading") {
      queued.current = { ms, play }
      setTimeMs(ms)
    } else void engine.current?.seek(ms, play)
  }
  const nextHandoff = handoffJump(d.timeline.handoffs, timeMs, d.replay.handoff_lead_ms)
  const jumpTo = (ms: number) => seekTo(ms, true)
  const tabs: ReplayTabs | undefined = sources.length < 2 ? undefined : {
    numbers: tabNumbers(sources), view, shown: source.tab ?? 1, segments: source.segments, agent: source.agent,
    setView: (picked) => {
      now.current.view = picked
      setViewState(picked)
      const wanted = sourceAt(d, sources, picked, now.current.timeMs, now.current.shown)
      if (wanted !== now.current.shown) switchTo(wanted, now.current.timeMs, now.current.playing)
    },
  }
  return {
    status, missing: source.replay.missing, error, timeMs, playing, waiting, noPage: status === "ready" && !paged, speed, address, mount, nextHandoff,
    play: () => (sources.length > 1 && now.current.ended ? seekTo(0, true) : engine.current?.play()),
    pause: () => engine.current?.pause(),
    seek: (ms) => (sources.length > 1 ? seekTo(ms, now.current.playing) : void engine.current?.seek(ms)),
    setSpeed: (value) => { setSpeedState(value); engine.current?.setSpeed(value) },
    jumpTo: (ms) => (sources.length > 1 ? jumpTo(ms) : void engine.current?.seek(ms, true)),
    jumpToHandoff: () => { if (nextHandoff !== null) (sources.length > 1 ? jumpTo(nextHandoff) : void engine.current?.seek(nextHandoff, true)) },
    retry: () => { setError(null); start.current = { ms: now.current.timeMs, play: false }; setAttempt((n) => n + 1) },
    ...(tabs && { tabs }),
  }
}
