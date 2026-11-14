// Agent avatars (DESIGN.md §15): one fixed dessert-blob per agent, drawn for cake (no third-party art).
// Flat colour (--avatar-1..6, never the verdict colours) + ink outline + white eyes with ink pupils. They idle (sway,
// bob, a little squash) and blink, each on its own beat; still under prefers-reduced-motion. Decoration only: the name
// is always written next to it, so the SVG is aria-hidden.
import { useId } from "react"
import { Badge } from "@/components/ui/badge"
import type { Certainty } from "@/data/types"
import { TAXONOMY, UNNAMED } from "@/lib/taxonomy"
import { cn } from "@/lib/utils"

type Shape = { d: string; eyeY: number; mouthY?: number; extra?: "band" | "chips" | "pleat" }
// mochi, gumdrop, macaron, donut, pudding, scoop, cookie (with a bite), dumpling. viewBox 0 0 48 48, ground at y 41.
const SHAPES: Shape[] = [
  { d: "M8 31 C8 18 15 10 24 10 C33 10 40 18 40 31 C40 38 34 41 24 41 C14 41 8 38 8 31 Z", eyeY: 25, mouthY: 31 },
  { d: "M10 39 C10 37 12 36 12 31 C12 18 17 9 24 9 C31 9 36 18 36 31 C36 36 38 37 38 39 C38 41 36 41 34 41 L14 41 C12 41 10 41 10 39 Z", eyeY: 24, mouthY: 30 },
  { d: "M7 21 C7 13 14 9 24 9 C34 9 41 13 41 21 L41 30 C41 37 34 41 24 41 C14 41 7 37 7 30 Z", eyeY: 18, mouthY: 23, extra: "band" },
  { d: "M24 10 A16 16 0 1 0 24.01 10 Z M24 23 A4.5 4.5 0 1 1 23.99 23 Z", eyeY: 16 },
  { d: "M14 15 C14 12 16 11 19 11 L29 11 C32 11 34 12 34 15 L39 36 C39.6 39.5 38 41 35 41 L13 41 C10 41 8.4 39.5 9 36 Z", eyeY: 25, mouthY: 31 },
  { d: "M8 26 C8 15 15 9 24 9 C33 9 40 15 40 26 C40 29 39.5 31 38 32.5 C37.5 37 34.5 37.5 33.5 34 C32.5 39 28.5 39.5 28 35 C27 40.5 21.5 40.5 21 35 C20 39 16 39 15.5 34.5 C14 37.5 10.5 37 10 32.5 C8.5 31 8 29 8 26 Z", eyeY: 22, mouthY: 28 },
  { d: "M31 11.6 A15.5 15.5 0 1 0 39.4 22.4 A8 8 0 0 1 31 11.6 Z", eyeY: 25, mouthY: 31, extra: "chips" },
  { d: "M8 31 C8 21 14 15 20.5 13.5 C21.5 10 26.5 10 27.5 13.5 C34 15 40 21 40 31 C40 38 33 41 24 41 C15 41 8 38 8 31 Z", eyeY: 27, mouthY: 33, extra: "pleat" },
]
const COLOURS = 6
const PHASES = 6

function hash(name: string) {
  let h = 2166136261
  for (const ch of name) { h ^= ch.codePointAt(0)!; h = Math.imul(h, 16777619) >>> 0 }
  return h
}

/** The fixed look of one agent: same name, same blob, same colour, same beat, everywhere. */
export function avatarOf(name: string) {
  const h = hash(name.trim().toLowerCase())
  return { shape: h % SHAPES.length, colour: 1 + (Math.floor(h / SHAPES.length) % COLOURS), phase: Math.floor(h / (SHAPES.length * COLOURS)) % PHASES }
}

export const AVATAR_SHAPES = ["mochi", "gumdrop", "macaron", "donut", "pudding", "scoop", "cookie", "dumpling"] as const

type Look = ReturnType<typeof avatarOf>
/** name = an agent (its fixed look); look = a given shape/colour (component overview); box = position inside a chart's SVG. */
export function AgentAvatar({ name = "", look, className, box }: { name?: string; look?: Look; className?: string; box?: { x: number; y: number; size: number } }) {
  const { shape, colour, phase } = look ?? avatarOf(name)
  const s = SHAPES[shape]
  const clip = `avatar-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`
  return (
    <svg viewBox="0 0 48 48" aria-hidden className={cn("crumb avatar shrink-0 overflow-visible", className)} data-phase={phase}
      x={box?.x} y={box?.y} width={box?.size} height={box?.size}>
      <g className="wob">
        <clipPath id={clip}><path d={s.d} fillRule="evenodd" /></clipPath>
        <path className={`f-avatar-${colour}`} d={s.d} fillRule="evenodd" />
        <g clipPath={`url(#${clip})`}>
          {s.extra === "band" && <rect className="f-cream" x="4" y="26" width="40" height="4.5" />}
          {s.extra === "chips" && <><ellipse className="f-outline faint" cx="15" cy="34" rx="1.8" ry="1.4" /><ellipse className="f-outline faint" cx="30" cy="35" rx="1.6" ry="1.3" /><ellipse className="f-outline faint" cx="13" cy="21" rx="1.5" ry="1.2" /></>}
        </g>
        {s.extra === "band" && <path className="line" d="M7.5 26 H40.5 M7.5 30.5 H40.5" />}
        {s.extra === "pleat" && <path className="line" d="M22 14.5 L23 17.5 M26 14.5 L25 17.5" />}
        <path className="line" d={s.d} />
        <g className="eyes">
          <ellipse className="sclera" cx="19" cy={s.eyeY} rx="3.6" ry="4.3" /><ellipse className="sclera" cx="29" cy={s.eyeY} rx="3.6" ry="4.3" />
          <circle className="pupil" cx="19.8" cy={s.eyeY + 0.8} r="1.9" /><circle className="pupil" cx="29.8" cy={s.eyeY + 0.8} r="1.9" />
        </g>
        {s.mouthY && <path className="o" strokeWidth="1.7" d={`M21.5 ${s.mouthY} q2.5 2.4 5 0`} />}
      </g>
    </svg>
  )
}

/** An agent's name as a tag (the session page's header): avatar + name and, when known, how sure the name is after it
 *  ("Claude in Chrome · likely", its sentence on hover), so the word reads as the name's and never as the verdict's;
 *  inside the name it qualifies, the word is lower case (a row's own tag beside the name keeps "Likely"). */
export function AgentTag({ name, certainty }: { name: string; certainty?: Certainty | null }) {
  const sure = certainty ? TAXONOMY.names[certainty] : null
  return (
    <Badge variant="tag" title={sure?.about}>
      <span className="inline-flex"><AgentAvatar name={name} className="size-4" /></span>{name}
      {sure && <><span aria-hidden>·</span>{sure.label.toLowerCase()}</>}
    </Badge>
  )
}

/** What the avatar takes at the end of an agent chart's axis: the avatar and a gap on each side of it. */
const TICK_AVATAR = 28
/** Two lines of text-xs at leading-4: the most a name takes on the axis. */
const TICK_LINES_HEIGHT = 32

/** Y-axis tick for agent charts: avatar + name. The name stays the label: it wraps to two lines in the axis's width
 *  (recharts passes it) and ends with "…" past that, the whole name on hover, since real names, like an agent
 *  category's, can be long. */
export function AgentTick({ x = 0, y = 0, width = 0, payload }: { x?: number; y?: number; width?: number; payload?: { value: string } }) {
  const name = payload?.value ?? "", room = Math.max(0, width - TICK_AVATAR)
  return (
    <g transform={`translate(${x},${y})`}>
      {name !== UNNAMED && <AgentAvatar name={name} box={{ x: -22, y: -10, size: 20 }} />}
      <foreignObject x={-TICK_AVATAR - room} y={-TICK_LINES_HEIGHT / 2} width={room} height={TICK_LINES_HEIGHT}>
        <div title={name} className="flex h-full items-center justify-end text-right text-xs leading-4 text-muted-foreground"><span className="line-clamp-2">{name}</span></div>
      </foreignObject>
    </g>
  )
}
