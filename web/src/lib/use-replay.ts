// The replay of one session for React (S5.4): a ReplayEngine (./replay-engine.ts) on the element `mount` is given, and
// what the stage, the controls and the timeline show. The page passes how to fetch a chunk (only pages call the API)
// and the cursor's label for each actor.
import { useEffect, useRef, useState } from "react"
import type { Actor, ReplayChunk, ReplayMissing, SessionDetail } from "@/data/types"
import { asApiError } from "@/data/api"
import { ReplayEngine, SPEEDS } from "./replay-engine"
import { handoffJump } from "./replay-timing"

export { SPEEDS }

/** loading: the player or its first chunks are on their way · ready · failed: they didn't come · missing: no replay. */
export type ReplayStatus = "loading" | "ready" | "failed" | "missing"

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
}

/** A replay is there to play unless it was deleted or never had anything in it ("dropped" still plays what is left). */
export const playable = (d: SessionDetail) => d.replay.chunks.length > 0 && d.replay.missing !== "freed" && d.replay.missing !== "none"

export function useReplay(d: SessionDetail, fetchChunk: (n: number, signal: AbortSignal) => Promise<ReplayChunk>,
  labels: Record<Actor, string>): ReplayState {
  const canPlay = playable(d)
  const [element, mount] = useState<HTMLDivElement | null>(null)
  const [status, setStatus] = useState<ReplayStatus>(canPlay ? "loading" : "missing")
  const [error, setError] = useState<string | null>(null)
  const [timeMs, setTimeMs] = useState(d.replay.start_ms)
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(false)
  const [paged, setPaged] = useState(true)
  const [speed, setSpeedState] = useState(SPEEDS[0])
  const [address, setAddress] = useState(d.replay.start_url)
  const [attempt, setAttempt] = useState(0)
  const engine = useRef<ReplayEngine | null>(null)

  // fetchChunk and labels are new functions and objects on every render; the session and the attempt say when the
  // player must start again.
  useEffect(() => {
    if (!element || !canPlay) return
    const controller = new AbortController()
    const fail = (e: unknown) => { if (!controller.signal.aborted) { setError(asApiError(e).message); setStatus("failed"); setPlaying(false) } }
    const current = new ReplayEngine({
      el: element, detail: d, labels, fetchChunk: (n) => fetchChunk(n, controller.signal),
      on: { time: setTimeMs, playing: setPlaying, waiting: setWaiting, address: setAddress, page: setPaged, failed: fail },
    })
    engine.current = current
    setStatus("loading")
    setPaged(true)
    setSpeedState(SPEEDS[0])
    current.start().then(() => { if (!controller.signal.aborted) setStatus("ready") }, fail)
    const observer = new ResizeObserver(() => current.resize())
    observer.observe(element)
    return () => {
      controller.abort()
      observer.disconnect()
      current.destroy()
      engine.current = null
    }
  }, [element, d, canPlay, attempt])

  const nextHandoff = handoffJump(d.timeline.handoffs, timeMs, d.replay.handoff_lead_ms)
  const jumpTo = (ms: number) => void engine.current?.seek(ms, true)
  return {
    status, missing: d.replay.missing, error, timeMs, playing, waiting, noPage: status === "ready" && !paged, speed, address, mount, nextHandoff,
    play: () => engine.current?.play(),
    pause: () => engine.current?.pause(),
    seek: (ms) => void engine.current?.seek(ms),
    setSpeed: (value) => { setSpeedState(value); engine.current?.setSpeed(value) },
    jumpTo,
    jumpToHandoff: () => { if (nextHandoff !== null) jumpTo(nextHandoff) },
    retry: () => { setError(null); setAttempt((n) => n + 1) },
  }
}
