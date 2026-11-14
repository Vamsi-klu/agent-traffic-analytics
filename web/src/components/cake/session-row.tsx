// One session in a list: its verdict, who acted (the agent's name badge with how sure the name is, as the session page
// shows it, or Unnamed), an Agent session's split, and its timeline (who acted when, at their places in the session). Agent rows are highlighted, bot rows are muted. DESIGN.md §6.1
import { Link } from "react-router"
import type { SessionSummary } from "@/data/types"
import { duration } from "@/lib/format"
import { UNNAMED } from "@/lib/taxonomy"
import { cn } from "@/lib/utils"
import { WORDS } from "@/lib/words"
import { AgentTag } from "./avatar"
import { CrumbHead } from "./crumb"
import { MiniTimeline, spansOf, timeLabel } from "./timeline"
import { ThinEvidenceTag, TurnsBadge, VERDICTS, VerdictBadge, isHighlighted } from "./verdict"

/** Who acted, as the row names it. */
function whoActed(s: SessionSummary) {
  if (s.agent) return s.agent
  if (s.verdict === "agent") return UNNAMED
  return s.verdict === "bot" ? VERDICTS.bot.label : WORDS.aHuman
}

export function SessionRow({ s, compact = false }: { s: SessionSummary; compact?: boolean }) {
  const hi = isHighlighted(s.verdict)
  const bot = s.verdict === "bot"
  return (
    <Link
      to={`/sessions/${s.id}`}
      data-highlight={hi || undefined}
      className={cn(
        "grid items-center rounded-xl border-2 border-line bg-card text-sm transition-transform",
        compact ? "grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 px-3 py-2" : "grid-cols-[7rem_minmax(0,1fr)_minmax(7rem,12rem)_7rem] gap-4 px-4 py-3 shadow-hard-sm hover:-translate-x-px hover:-translate-y-px hover:shadow-hard max-md:grid-cols-[minmax(0,1fr)_auto] max-md:gap-y-2",
        hi && (compact ? "border-l-6 border-l-agent" : "border-l-8 border-l-agent"),
        bot && "border-border opacity-60 shadow-none hover:opacity-100",
      )}
    >
      <VerdictBadge verdict={s.verdict} className="justify-self-start" />
      <span className="flex min-w-0 flex-col gap-0.5">
        <b className="flex min-w-0 items-center gap-1.5 font-extrabold">
          {hi && <CrumbHead className="size-5 shrink-0" title={WORDS.rowMarker} />}
          {s.agent && !bot ? <AgentTag name={s.agent} certainty={s.certainty} />
            : <span className={cn("truncate", hi && !s.agent && "font-bold text-muted-foreground")}>{whoActed(s)}</span>}
          {s.evidence && <ThinEvidenceTag />}
        </b>
        {!compact && (
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {s.agent_turns && <TurnsBadge turns={s.agent_turns} />}
            {s.pages} page{s.pages === 1 ? "" : "s"} · {duration(s.duration_ms)}
          </span>
        )}
      </span>
      <span className={cn(compact ? "col-span-2" : "max-md:col-span-2 max-md:row-start-2")}>
        {bot ? <span className="text-xs text-faint-foreground">{WORDS.botRow}</span>
          : <MiniTimeline spans={s.segments ? spansOf(s.segments, s.duration_ms) : []} label={s.segments ? timeLabel(s.segments) : WORDS.whoUnknown} />}
      </span>
      {!compact && <span className="text-right text-xs text-faint-foreground max-md:row-start-1 max-md:col-start-2">{s.when}</span>}
    </Link>
  )
}
