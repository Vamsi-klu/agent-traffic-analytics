// Who acted when: the segmented bar (rows) and the session timeline (replay page). DESIGN.md §6
// The components draw percents; spansOf() and timelineView() turn the API's milliseconds (src/data/types.ts) into them.
// On the replay page the session timeline is also the replay's position control: click or drag to move the
// replay, arrow keys step, Home and End go to the ends. A session of more than one tab has a line per tab in its row
// (TabLines) and a track per tab on its page (TabTimeline), on the session's one clock.
import { Fragment, useRef, type KeyboardEvent, type PointerEvent, type Ref } from "react"
import type { Segment, TabTrack, Timeline } from "@/data/types"
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
/** Each kind's fill, in bars, timelines and the legend's swatches: the verdict colours, Unknown's dots. */
export const segClass: Record<SegKind, string> = { h: "bg-human", a: "bg-agent", u: "pattern-dots" }
const segName: Record<SegKind, string> = { h: TAXONOMY.verdicts.human.label, a: TAXONOMY.verdicts.agent.label, u: TAXONOMY.unsure.label }
/** How far an arrow key moves the replay. */
const KEY_STEP_MS = 5000
/** Hand-off labels closer than this share of the timeline would touch at the narrowest width (485 px): the later one
 *  takes the other row. ("Hand-off to agent 0:38" is a little longer than the earlier "Agent takes over 0:38".) */
const LABEL_ROOM_PCT = 50

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

/** The bar's height: sm in rows, lg on the session page, xs for each tab's line in a row (TabLines). */
const MINI_HEIGHT = { xs: "h-2.5 minimal:h-1.5", sm: "h-3.5 minimal:h-2", lg: "h-7 minimal:h-3" }

/** Small segmented bar. With spans: a row's timeline, each stretch at its place in the session with the gaps between
 *  them (spansOf), read aloud by time (label: timeLabel); without: an actor's share of the actions in time order of
 *  who acts first (segs, the session page's share bar), read as those shares. The label is the bar's text for screen
 *  readers only (DESIGN.md §11), no hover box: the rows show who acted where, the session page writes the shares. */
export function MiniTimeline({ human = 0, agent = 0, unsure = 0, segs, spans, label: given, size = "sm", className }: {
  human?: number; agent?: number; unsure?: number; segs?: Seg[]; spans?: Span[]; label?: string; size?: keyof typeof MINI_HEIGHT; className?: string
}) {
  const label = given ?? `${segName.h} ${human}%, ${segName.a} ${agent}%, ${segName.u} ${unsure}%`
  const frame = cn("w-full min-w-20 overflow-hidden rounded-full border-2 border-line bg-card minimal:border-0 minimal:bg-secondary", MINI_HEIGHT[size], className)
  if (spans) {
    return (
      <div role="img" aria-label={label} className={cn("relative", frame)}>
        {spans.map((s, i) => <i key={i} className={cn("absolute inset-y-0 block", segClass[s.kind])} style={{ left: `${s.left}%`, width: `${s.width}%` }} />)}
      </div>
    )
  }
  return (
    <div role="img" aria-label={label} className={cn("flex gap-0.5", frame)}>
      {segsFrom(human, agent, unsure, segs).map((s, i) => (
        <i key={i} className={cn("block h-full", segClass[s.kind])} style={{ width: `${s.pct}%` }} />
      ))}
    </div>
  )
}

/** A row's timeline of a session with more than one tab: a thin line per tab, Tab 1 on top, each stretch at its place
 *  in the session (the API's tabs: TabTrack), each line read aloud with its tab's name. */
export function TabLines({ tabs, durationMs }: { tabs: TabTrack[]; durationMs: number }) {
  return (
    <div className="flex flex-col gap-0.5">
      {tabs.map((tab, i) => (
        <MiniTimeline key={i} size="xs" spans={spansOf(tab.segments, durationMs)}
          label={`${WORDS.tab(i + 1)}: ${tab.segments.length ? timeLabel(tab.segments) : WORDS.whoUnknown}`} />
      ))}
    </div>
  )
}

/** The replay's position on the timeline: where it is (ms), how it reads ("0:52 of 1:36 · Agent") and where to go. */
export type TimelineSeek = { durationMs: number; valueMs: number; valueText: string; onSeek: (ms: number) => void }

/** The timeline as the replay's position control: the slider's props (role, value, keys) for the element that takes
 *  the focus, the pointer's for each bar (click or drag), and the bar a pointer's place is measured in (every bar of a
 *  timeline is as wide as the others). */
function useSeekControl(seek: TimelineSeek | undefined) {
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
  const slider = seek && {
    role: "slider", tabIndex: 0, "aria-label": WORDS.replayPosition, "aria-valuemin": 0, "aria-valuemax": Math.round(seek.durationMs),
    "aria-valuenow": Math.round(seek.valueMs), "aria-valuetext": seek.valueText, onKeyDown: key,
  }
  const pointer = seek && { onPointerDown: press, onPointerMove: drag, onPointerUp: release, onPointerCancel: release }
  return { bar, slider, pointer }
}

/** One bar of the session timeline: its segments at their places, the playhead, and around it the hand-off marks
 *  (labels above it); padded at the top for the labels' rows (none on a tab's track without hand-offs). seekable: a
 *  pointer moves the replay; focusable: the bar itself is the control the keys move (a tab's track is not: the
 *  tracks together are). */
function TrackBar({ spans, handoffs, playhead, barRef, control, seekable, focusable, padded = true }: {
  spans: Span[]; handoffs: HandoffMark[]; playhead?: number; barRef?: Ref<HTMLDivElement>; control?: object; seekable: boolean
  focusable: boolean; padded?: boolean
}) {
  return (
    <div className={cn("relative", handoffs.some((h) => h.row) ? "pt-14" : (padded || handoffs.length > 0) && "pt-7")}>
      <div ref={barRef} {...control} data-timeline-bar=""
        className={cn("relative h-9 touch-none overflow-hidden rounded-xl border-2 border-line bg-card minimal:border-0 minimal:bg-secondary", seekable && "cursor-pointer", focusable && "outline-none focus-visible:ring-3 focus-visible:ring-ring/50")}>
        {spans.map((s, i) => (
          <div key={i} data-segment={s.kind}
            className={cn("absolute inset-y-0", segClass[s.kind], i > 0 && "border-l-2 border-card")} style={{ left: `${s.left}%`, width: `${s.width}%` }} />
        ))}
        {playhead !== undefined && <span aria-hidden data-playhead="" className="absolute inset-y-0 w-1 -translate-x-1/2 rounded-sm bg-foreground" style={{ left: `${playhead}%` }} />}
      </div>
      <div aria-hidden className="pointer-events-none absolute inset-x-0.5 top-0 -bottom-1">
        {handoffs.map((h) => (
          <span key={`${h.at}-${h.label}`} data-handoff="" className={cn("absolute bottom-0 border-l-3 border-dashed border-foreground minimal:border-l-2", h.row ? "top-7" : "top-0")} style={{ left: `${h.at}%` }}>
            <b className={cn("absolute top-0 z-10 rounded-full", h.at > 70 ? "-translate-x-full" : h.at < 30 ? "-translate-x-2" : "-translate-x-1/2", " border-2 border-line bg-highlight px-2 text-xs font-extrabold whitespace-nowrap text-highlight-foreground minimal:border-0 minimal:font-semibold")}>{h.label}</b>
          </span>
        ))}
      </div>
    </div>
  )
}

function Ticks({ ticks }: { ticks: string[] }) {
  return <div className="mt-1 flex justify-between font-mono text-xs text-faint-foreground">{ticks.map((t) => <span key={t}>{t}</span>)}</div>
}

/** Replay timeline: segments + hand-off markers + playhead, positions as % of the session. With `seek` it is the
 *  replay's position control, which says who acts at its position (valueText). The segments' colours are the verdicts',
 *  named by the legend beside the timeline: no hover box on them. */
export function SessionTimeline({ spans, handoffs, playhead, ticks, seek }: {
  spans: Span[]; handoffs: HandoffMark[]; playhead?: number; ticks: string[]; seek?: TimelineSeek
}) {
  const { bar, slider, pointer } = useSeekControl(seek)
  return (
    <div>
      <TrackBar spans={spans} handoffs={handoffs} playhead={playhead} barRef={bar} control={slider && { ...slider, ...pointer }}
        seekable={seek !== undefined} focusable={seek !== undefined} />
      <Ticks ticks={ticks} />
    </div>
  )
}

/** One tab's track on the session page's timeline (TabTimeline): its name, its segments and hand-offs (timelineView of
 *  its runs), and whether it is the tab the replay shows. */
export type TabTimelineTrack = { label: string; spans: Span[]; handoffs: HandoffMark[]; shown: boolean }

/** The session timeline of a session with more than one tab: a track per tab, Tab 1 on top, its name beside it (the
 *  tab the replay shows in the text colour, the others muted), one playhead across them and one clock under them. With
 *  `seek` the tracks together are the replay's position control: any track can be clicked or dragged, and the keys
 *  move the one position. */
export function TabTimeline({ tracks, playhead, ticks, seek }: {
  tracks: TabTimelineTrack[]; playhead?: number; ticks: string[]; seek?: TimelineSeek
}) {
  const { bar, slider, pointer } = useSeekControl(seek)
  return (
    <div>
      <div {...slider} data-tab-timeline="" className={cn("grid grid-cols-[3.5rem_minmax(0,1fr)] items-end gap-x-3 gap-y-2 rounded-xl", seek && "outline-none focus-visible:ring-3 focus-visible:ring-ring/50")}>
        {tracks.map((track, i) => (
          <Fragment key={track.label}>
            <span data-tab-label="" data-shown={track.shown || undefined} className={cn("pb-2 text-xs font-bold", track.shown ? "text-foreground" : "text-muted-foreground")}>{track.label}</span>
            <TrackBar spans={track.spans} handoffs={track.handoffs} playhead={playhead} barRef={i === 0 ? bar : undefined} control={pointer}
              seekable={seek !== undefined} focusable={false} padded={false} />
          </Fragment>
        ))}
      </div>
      <div className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-x-3"><span /><Ticks ticks={ticks} /></div>
    </div>
  )
}
