// One layer of "Why this verdict" (1 Name, 2 Verification, 3 Environment, 4 Behavior), from /api/session/<id>. DESIGN.md §6
// Each reason is its sentence and, under it in smaller, fainter type, what was seen (its detail), when it has one.
// Every layer is shown, a layer that is off too (dashed, "Off here"), with the reasons cake gave; a layer cake gave no
// reason for still says what it means (off: it didn't run; no hit: nothing found), so no layer is ever a blank box.
import { Activity, CircleSlash, Fingerprint, Keyboard, Monitor, MousePointerClick, ScrollText, Server, Tag, type LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { LayerId, LayerReasons, Reason, ReasonKind } from "@/data/types"
import { cn } from "@/lib/utils"
import { WORDS } from "@/lib/words"
import { WhoBadge } from "./verdict"

/** The four layers' numbers and names, as the reasons panel and the settings show them. */
export const LAYERS: Record<LayerId, { n: number; name: string }> = {
  name: { n: 1, name: "Name" },
  verify: { n: 2, name: "Verification" },
  environment: { n: 3, name: "Environment" },
  behavior: { n: 4, name: "Behavior" },
}

/** The icon for each kind of evidence. */
const ICON: Record<ReasonKind, LucideIcon> = {
  user_agent: Tag, server: Server, page: Fingerprint, browser: Monitor, clicks: MousePointerClick, keys: Keyboard, motion: ScrollText, model: Activity,
}
const toneClass = { agent: "text-agent-foreground", human: "text-human-foreground", none: "text-faint-foreground" }

/** A layer's conclusion: its state, with how sure it is of that conclusion (bold, on the highlighter) when the API gives
 *  a percent; a behavior layer that found a human and an agent taking turns says Human + agent, its percent how sure
 *  it is that an agent took part. */
function LayerState({ layer: { state, percent } }: { layer: LayerReasons }) {
  if (state === "no_hit") return <Badge variant="tag">No findings</Badge>
  if (state === "off") return <Badge variant="tag">Off here</Badge>
  return <WhoBadge who={state} percent={percent} />
}

/** What a layer without reasons says. */
const UNEXPLAINED: Partial<Record<LayerReasons["state"], string>> = { off: WORDS.layerOff, no_hit: WORDS.layerNoHit }

/** A reason: its sentence in the tone's colour and, under it, smaller and fainter, what was seen (its detail). */
function ReasonLine({ reason }: { reason: Reason }) {
  const Icon = ICON[reason.kind]
  return (
    <li className={cn("flex items-start gap-2 text-sm", toneClass[reason.tone])}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span className="flex flex-col gap-0.5">
        <span>{reason.text}</span>
        {reason.detail && <span className="text-xs text-faint-foreground">{reason.detail}</span>}
      </span>
    </li>
  )
}

export function ReasonLayer({ layer }: { layer: LayerReasons }) {
  const { n, name } = LAYERS[layer.layer]
  const off = layer.state === "off"
  const unexplained = layer.reasons.length ? null : UNEXPLAINED[layer.state]
  return (
    <section data-layer={layer.layer} data-state={layer.state} className={cn("overflow-hidden rounded-xl border-2 bg-card", off ? "border-dashed border-border" : "border-line")}>
      <header className={cn("flex items-center gap-2 border-b-2 border-border px-3 py-2 font-extrabold", off ? "text-faint-foreground" : "bg-muted")}>
        <span className={cn("inline-flex size-6 items-center justify-center rounded-full font-heading text-sm", off ? "bg-unsure text-card" : "bg-foreground text-background")}>{n}</span>
        {name}<span className="ml-auto"><LayerState layer={layer} /></span>
      </header>
      <ul className="flex flex-col gap-2 px-3 py-2">
        {layer.reasons.map((r, i) => <ReasonLine key={`${i}-${r.text}`} reason={r} />)}
        {unexplained && <li className="flex items-start gap-2 text-sm text-faint-foreground"><CircleSlash className="mt-0.5 size-4 shrink-0" aria-hidden /><span>{unexplained}</span></li>}
      </ul>
    </section>
  )
}
