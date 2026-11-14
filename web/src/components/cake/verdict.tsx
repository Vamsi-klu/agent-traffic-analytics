// The session categories (D39) — one colour, one icon, one word each, everywhere. DESIGN.md §3.1
// The verdict (Human, Agent, Bot) is VerdictBadge, with ThinEvidenceTag beside a Human session cake couldn't tell; an
// Agent session's split (Agent only, Human + agent) is TurnsBadge; which agent is AgentTag (avatar.tsx) with how sure
// its name is inside it, or UnnamedTag. A stretch or a layer that couldn't tell reads Unknown in the same badge. The words are
// judging.en.json's (src/lib/taxonomy.ts).
import { Bot, CircleDashed, CircleHelp, Cpu, Hand, User, type LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { Actor, AgentTurns, Verdict } from "@/data/types"
import { TAXONOMY } from "@/lib/taxonomy"
import { cn } from "@/lib/utils"
import type { SegKind } from "./timeline"

/** What a badge can show: a verdict, or Unknown for a stretch, an action or a layer that couldn't tell. */
type Look = Verdict | "unknown"
const ICON: Record<Look, LucideIcon> = { human: User, agent: Bot, unknown: CircleHelp, bot: Cpu }

export const VERDICTS: Record<Look, { label: string; icon: LucideIcon }> = {
  human: { label: TAXONOMY.verdicts.human.label, icon: ICON.human },
  agent: { label: TAXONOMY.verdicts.agent.label, icon: ICON.agent },
  unknown: { label: TAXONOMY.unsure.label, icon: ICON.unknown },
  bot: { label: TAXONOMY.verdicts.bot.label, icon: ICON.bot },
}

/** A stretch or an action the behavior model couldn't tell ("unsure") reads Unknown. */
const lookOf = (who: Look | Actor): Look => (who === "unsure" ? "unknown" : who)

/** Agent sessions, where an AI agent acted for a human: always highlighted (DESIGN.md §1.1). */
export const isHighlighted = (v: Verdict) => v === "agent"

const dot: Record<Look, string> = {
  human: "bg-human",
  agent: "bg-agent",
  unknown: "bg-unsure",
  bot: "bg-faint-foreground",
}

/** How sure cake is of a verdict, after its word: bold, on the highlighter (the session page's verdict and layers). */
function Percent({ value }: { value?: number | null }) {
  if (value === undefined || value === null) return null
  return <><span aria-hidden>·</span><b className="rounded-sm bg-highlight px-1 font-extrabold text-highlight-foreground">{`${value}%`}</b></>
}

/** A verdict, or who acted in a stretch, an action or a layer ("unsure" and "unknown" read Unknown); percent: how sure
 *  cake is of it. */
export function VerdictBadge({ verdict, percent, className }: { verdict: Look | Actor; percent?: number | null; className?: string }) {
  const v = lookOf(verdict)
  const { label, icon: Icon } = VERDICTS[v]
  return (
    <Badge variant={v} data-category={v} className={cn("pl-0.5", className)}>
      <span className={cn("inline-flex size-4.5 items-center justify-center rounded-full text-card", dot[v])}>
        <Icon className="size-3!" aria-hidden />
      </span>
      {label}<Percent value={percent} />
    </Badge>
  )
}

/** The icon of each split of an Agent session: the badge, the top block's links. */
export const TURNS_ICON: Record<AgentTurns, LucideIcon> = { agent_only: Bot, human_agent: Hand }

/** Inside Agent, in the Agent badge's shape and colours: Agent only with the agent's dot, Human + agent with a half
 *  human, half agent dot (its hand-offs are on the timeline). */
export function TurnsBadge({ turns, percent, className }: { turns: AgentTurns; percent?: number | null; className?: string }) {
  const { label, about } = TAXONOMY.turns[turns]
  const Icon = TURNS_ICON[turns]
  return (
    <Badge variant="agent" data-category={turns} className={cn("pl-0.5", className)} title={about}>
      <span className={cn("inline-flex size-4.5 items-center justify-center rounded-full text-card", turns === "agent_only" ? dot.agent : "pattern-mixed-solid")}>
        <Icon className="size-3!" aria-hidden />
      </span>
      {label}<Percent value={percent} />
    </Badge>
  )
}

/** Thin evidence: a Human session cake couldn't tell (D39), beside its Human badge; the reasons say why. */
export function ThinEvidenceTag({ className }: { className?: string }) {
  return <Badge variant="thin" className={className} title={TAXONOMY.evidence.thin.about}><CircleDashed aria-hidden />{TAXONOMY.evidence.thin.label}</Badge>
}

/** Who acted somewhere (a layer's conclusion, a page of the visit): a verdict, or a human and an agent taking turns. */
export function WhoBadge({ who, percent, className }: { who: Look | Actor | "human_agent"; percent?: number | null; className?: string }) {
  if (who === "human_agent") return <TurnsBadge turns={who} percent={percent} className={className} />
  return <VerdictBadge verdict={who} percent={percent} className={className} />
}

/** An agent no product or tool name fits: what was seen is in its reasons. */
export function UnnamedTag({ className }: { className?: string }) {
  return <Badge variant="tag" className={className} title={TAXONOMY.names.unnamed.about}>{TAXONOMY.names.unnamed.label}</Badge>
}

/** Small square colour key, used in legends and next to KPI labels. */
export function Swatch({ kind, className }: { kind: SegKind | "mixed"; className?: string }) {
  const cls = kind === "h" ? "bg-human" : kind === "a" ? "bg-agent" : kind === "mixed" ? "pattern-mixed-solid" : "pattern-dots"
  return <span aria-hidden className={cn("inline-block size-3 shrink-0 rounded-sm border-2 border-line", cls, className)} />
}

export function Legend({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-bold text-muted-foreground", className)}>
      <span className="inline-flex items-center gap-1.5"><Swatch kind="h" />{VERDICTS.human.label}</span>
      <span className="inline-flex items-center gap-1.5"><Swatch kind="a" />{VERDICTS.agent.label}</span>
      <span className="inline-flex items-center gap-1.5"><Swatch kind="u" />{VERDICTS.unknown.label}</span>
    </div>
  )
}
