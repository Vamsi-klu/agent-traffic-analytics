// Who acted when: the segmented bar (rows) and the session timeline (replay page). DESIGN.md §6
// The components draw percents; spansOf() and timelineView() turn the API's milliseconds (src/data/types.ts) into them.
// On the replay page the session timeline is also the replay's position control: click or drag to move the
// replay, arrow keys step, Home and End go to the ends.
import { useRef, type KeyboardEvent, type PointerEvent } from "react"
import type { Segment, Timeline } from "@/data/types"
import { clock } from "@/lib/format"
import { TAXONOMY } from "@/lib/taxonomy"
import { cn } from "@/lib/utils"
import { WORDS } from "@/lib/words"

export type SegKind = "h" | "a" | "u"
/** A stretch of a bar drawn in time order (rows: widths only). */
export type Seg = { kind: SegKind; pct: number }
/** A stretch of the session timeline at its place: left and width as percents of the session, gaps left empty. */
export type Span = { kind: SegKind; left: number; width: number }
/** A hand-off on the session timeline: where (percent), its label, and the label's row (1 when it would touch the
 *  label before it, so no two labels overlap at any width). */
export type HandoffMark = { at: number; label: string; row: 0 | 1 }

const KIND: Record<Segment["who"], SegKind> = { human: "h", agent: "a", unsure: "u" }
const segClass: Record<SegKind, string> = { h: "bg-human", a: "bg-agent", u: "pattern-dots" }
const segName: Record<SegKind, string> = { h: TAXONOMY.verdicts.human.label, a: TAXONOMY.verdicts.agent.label, u: TAXONOMY.unsure.label }
/** How far an arrow key moves the replay. */
const KEY_STEP_MS = 5000
/** Hand-off labels closer than this share of the timeline would touch at the narrowest width (485 px): the later one
 *  takes the other row. */
const LABEL_ROOM_PCT = 45

/** A length or position as a percent of a session (ms × 100 first, so whole percents stay exact). */
export const pctOf = (ms: number, totalMs: number) => (totalMs > 0 ? (ms * 100) / totalMs : 0)

/** How a bar drawn in time reads aloud: who acted from when to when ("Agent 0:00–0:31, Human 0:40–1:27"). */
export const timeLabel = (segments: Segment[]) =>
  segments.map((s) => `${segName[KIND[s.who]]} ${clock(s.start_ms)}–${clock(s.end_ms)}`).join(", ")

/** The API's segments at their places in the session. */
export const spansOf = (segments: Segment[], durationMs: number): Span[] =>
  segments.map((s) => ({ kind: KIND[s.who], left: pctOf(s.start_ms, durationMs), width: pctOf(s.end_ms - s.start_ms, durationMs) }))

// Tick labels: the first step from this list that cuts the session into at most MAX_TICK_STEPS parts; an inner tick
// closer to the end than half a step is left out so two labels never touch.
const TICK_STEPS_MS = [5_000, 10_000, 15_000, 30_000, 60_000, 120_000, 300_000, 600_000, 900_000, 1_800_000, 3_600_000]
const MAX_TICK_STEPS = 4

function ticks(durationMs: number) {
  const step = TICK_STEPS_MS.find((s) => durationMs / s <= MAX_TICK_STEPS) ?? TICK_STEPS_MS[TICK_STEPS_MS.length - 1]
  const inner: number[] = []
  for (let t = step; t < durationMs - step / 2; t += step) inner.push(t)
  return [0, ...inner, durationMs].map(clock)
}

/** A session's timeline from the API as SessionTimeline's props. compact = previews: labels without times, ticks at
 *  the two ends only. */
export function timelineView(t: Timeline, { playheadMs, compact = false }: { playheadMs?: number; compact?: boolean } = {}) {
  return {
    spans: spansOf(t.segments, t.duration_ms),
    handoffs: t.handoffs.reduce<HandoffMark[]>((marks, h) => {
      const word = h.to === "agent" ? WORDS.toAgent : WORDS.toHuman
      const at = pctOf(h.at_ms, t.duration_ms), before = marks[marks.length - 1]
      const row = before && at - before.at < LABEL_ROOM_PCT ? ((1 - before.row) as 0 | 1) : 0
      return [...marks, { at, label: compact ? word : `${word} ${clock(h.at_ms)}`, row }]
    }, []),
    playhead: playheadMs === undefined ? undefined : pctOf(playheadMs, t.duration_ms),
    ticks: compact ? [clock(0), clock(t.duration_ms)] : ticks(t.duration_ms),
  }
}

/** A session's shares as bar segments in the order each actor first acts on its timeline (an actor the timeline doesn't
 *  show comes last), so a share bar under the session timeline reads in the timeline's order. */
export function segsInTimeOrder(segments: Segment[], share: { human: number; agent: number; unsure: number }): Seg[] {
  const order: SegKind[] = []
  for (const kind of [...segments.map((s) => KIND[s.who]), "h", "a", "u"] as SegKind[]) if (!order.includes(kind)) order.push(kind)
  const pct: Record<SegKind, number> = { h: share.human, a: share.agent, u: share.unsure }
  return order.filter((kind) => pct[kind] > 0).map((kind) => ({ kind, pct: pct[kind] }))
}

export function segsFrom(human: number, agent: number, unsure: number, segs?: Seg[]): Seg[] {
  if (segs) return segs
  return ([["h", human], ["a", agent], ["u", unsure]] as [SegKind, number][]).filter(([, p]) => p > 0).map(([kind, pct]) => ({ kind, pct }))
}

/** Small segmented bar. With spans: a row's timeline, each stretch at its place in the session with the gaps between
 *  them (spansOf), read aloud by time (label: timeLabel); without: an actor's share of the actions in time order of
 *  who acts first (segs, the session page's share bar), read as those shares. */
export function MiniTimeline({ human = 0, agent = 0, unsure = 0, segs, spans, label: given, size = "sm", className }: {
  human?: number; agent?: number; unsure?: number; segs?: Seg[]; spans?: Span[]; label?: string; size?: "sm" | "lg"; className?: string
}) {
  const label = given ?? `${segName.h} ${human}%, ${segName.a} ${agent}%, ${segName.u} ${unsure}%`
  const frame = cn("w-full min-w-20 overflow-hidden rounded-full border-2 border-line bg-card", size === "lg" ? "h-7" : "h-3.5", className)
  if (spans) {
    return (
      <div role="img" aria-label={label} title={label} className={cn("relative", frame)}>
        {spans.map((s, i) => <i key={i} className={cn("absolute inset-y-0 block", segClass[s.kind])} style={{ left: `${s.left}%`, width: `${s.width}%` }} />)}
      </div>
    )
  }
  return (
    <div role="img" aria-label={label} title={label} className={cn("flex gap-0.5", frame)}>
      {segsFrom(human, agent, unsure, segs).map((s, i) => (
        <i key={i} className={cn("block h-full", segClass[s.kind])} style={{ width: `${s.pct}%` }} />
      ))}
    </div>
  )
}

/** The replay's position on the timeline: where it is (ms), how it reads ("0:52 of 1:36 · Agent") and where to go. */
export type TimelineSeek = { durationMs: number; valueMs: number; valueText: string; onSeek: (ms: number) => void }

/** Replay timeline: segments + hand-off markers + playhead, positions as % of the session. With `seek` it is the
 *  replay's position control. */
export function SessionTimeline({ spans, handoffs, playhead, ticks, seek }: {
  spans: Span[]; handoffs: HandoffMark[]; playhead?: number; ticks: string[]; seek?: TimelineSeek
}) {
  const bar = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  /** The session moment under a pointer: measured inside the bar's frame, where the segments are placed. */
  const msAt = (clientX: number) => {
    const el = bar.current
    if (!el || !seek || !el.clientWidth) return 0
    const share = (clientX - el.getBoundingClientRect().left - el.clientLeft) / el.clientWidth
    return Math.min(1, Math.max(0, share)) * seek.durationMs
  }
  const press = (e: PointerEvent<HTMLDivElement>) => {
    if (!seek) return
    dragging.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    seek.onSeek(msAt(e.clientX))
  }
  const drag = (e: PointerEvent<HTMLDivElement>) => { if (dragging.current) seek?.onSeek(msAt(e.clientX)) }
  const release = () => { dragging.current = false }
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!seek) return
    const to = { ArrowLeft: seek.valueMs - KEY_STEP_MS, ArrowDown: seek.valueMs - KEY_STEP_MS, ArrowRight: seek.valueMs + KEY_STEP_MS,
      ArrowUp: seek.valueMs + KEY_STEP_MS, Home: 0, End: seek.durationMs }[e.key]
    if (to === undefined) return
    e.preventDefault()
    seek.onSeek(Math.min(seek.durationMs, Math.max(0, to)))
  }
  const control = seek && {
    role: "slider", tabIndex: 0, "aria-label": WORDS.replayPosition, "aria-valuemin": 0, "aria-valuemax": Math.round(seek.durationMs),
    "aria-valuenow": Math.round(seek.valueMs), "aria-valuetext": seek.valueText,
    onPointerDown: press, onPointerMove: drag, onPointerUp: release, onPointerCancel: release, onKeyDown: key,
  }
  return (
    <div>
      <div className={cn("relative", handoffs.some((h) => h.row) ? "pt-14" : "pt-7")}>
        <div ref={bar} {...control} data-timeline-bar=""
          className={cn("relative h-9 touch-none overflow-hidden rounded-xl border-2 border-line bg-card", seek && "cursor-pointer outline-none focus-visible:ring-3 focus-visible:ring-ring/50")}>
          {spans.map((s, i) => (
            <div key={i} title={segName[s.kind]} data-segment={s.kind}
              className={cn("absolute inset-y-0", segClass[s.kind], i > 0 && "border-l-2 border-card")} style={{ left: `${s.left}%`, width: `${s.width}%` }} />
          ))}
          {playhead !== undefined && <span aria-hidden data-playhead="" className="absolute inset-y-0 w-1 -translate-x-1/2 rounded-sm bg-foreground" style={{ left: `${playhead}%` }} />}
        </div>
        <div aria-hidden className="pointer-events-none absolute inset-x-0.5 top-0 -bottom-1">
          {handoffs.map((h) => (
            <span key={`${h.at}-${h.label}`} data-handoff="" className={cn("absolute bottom-0 border-l-3 border-dashed border-foreground", h.row ? "top-7" : "top-0")} style={{ left: `${h.at}%` }}>
              <b className={cn("absolute top-0 z-10 rounded-full", h.at > 70 ? "-translate-x-full" : h.at < 30 ? "-translate-x-2" : "-translate-x-1/2", " border-2 border-line bg-highlight px-2 text-xs font-extrabold whitespace-nowrap text-highlight-foreground")}>{h.label}</b>
            </span>
          ))}
        </div>
      </div>
      <div className="mt-1 flex justify-between font-mono text-xs text-faint-foreground">{ticks.map((t) => <span key={t}>{t}</span>)}</div>
    </div>
  )
}
