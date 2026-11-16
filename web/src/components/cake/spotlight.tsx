// The Agent block at the top of the dashboard (DESIGN.md §6.1), and its "none yet" version.
import { Play, TrendingDown, TrendingUp } from "lucide-react"
import { Link } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { Overview } from "@/data/types"
import { percent } from "@/lib/format"
import { TAXONOMY, UNNAMED } from "@/lib/taxonomy"
import { WORDS } from "@/lib/words"
import { AgentAvatar } from "./avatar"
import { Hint, InfoTip } from "./bits"
import { Crumb, CrumbHead } from "./crumb"
import { SessionRow } from "./session-row"
import { Legend } from "./verdict"

function Eyebrow() {
  return <span className="flex items-center gap-2 text-sm font-extrabold text-agent-foreground"><CrumbHead className="size-7" />{WORDS.agentSessions}</span>
}

/** The top of /api/overview: Agent counts, the change since last week, each agent by name with its avatar (Unnamed
 *  together, with the one grey avatar), and the newest three. Agent only and Human + agent aren't split here: the main
 *  dashboard counts Human and Agent; the session list's filter and the categories block name the two kinds. */
export function Spotlight({ overview }: { overview: Overview }) {
  const { counts, latest_agent: latest } = overview
  // all time has no earlier range: no comparison at all, rather than a made-up 0
  const delta = overview.agent_last_week === null ? null : counts.agent - overview.agent_last_week
  const Trend = delta !== null && delta < 0 ? TrendingDown : TrendingUp
  return (
    <Card variant="highlight" aria-labelledby="spot-title">
      <CardContent className="grid gap-5 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="flex flex-col gap-3">
          <Eyebrow />
          <div className="flex flex-wrap items-end gap-3">
            <span className="font-heading text-6xl leading-none font-semibold">{counts.agent}</span>
            {delta !== null && <Badge variant="tag" className="mb-1"><Trend aria-hidden />{delta < 0 ? "−" : "+"}{Math.abs(delta)} compared to last week</Badge>}
          </div>
          <div className="flex items-center gap-2"><h3 id="spot-title" className="text-lg font-semibold">{WORDS.actedForHuman}</h3><InfoTip label={WORDS.agentSessions} lines={WORDS.about.agents} /></div>
          <ul aria-label={WORDS.agentsByName} className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            {overview.agents_seen.map(({ name, sessions }) => (
              <li key={name ?? UNNAMED}>
                {name ? (
                  <Link to={`/sessions?filter=agent&agent=${encodeURIComponent(name)}`} className="flex items-center gap-x-1.5 hover:underline">
                    <AgentAvatar name={name} className="size-5" /><b>{sessions}</b><span className="font-bold">{name}</span>
                  </Link>
                ) : (
                  <Hint text={TAXONOMY.names.unnamed.about} focusable>
                    <span className="flex items-center gap-x-1.5"><AgentAvatar name={UNNAMED} className="size-5" /><b>{sessions}</b><span className="font-bold text-muted-foreground">{UNNAMED}</span></span>
                  </Hint>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild><Link to="/sessions?filter=agent"><Play aria-hidden />{WORDS.watchReplays}</Link></Button>
            <span className="text-xs text-muted-foreground">{`${percent(counts.agent, counts.all)}% of all sessions`}</span>
          </div>
        </div>
        <Card variant="flat" size="sm">
          <CardContent className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2"><b className="text-sm">Latest</b><Legend /></div>
            {latest.length ? latest.map((s) => <SessionRow key={s.id} s={s} compact />) : <p className="text-sm text-muted-foreground">No sessions match the selected filters.</p>}
          </CardContent>
        </Card>
      </CardContent>
    </Card>
  )
}

/** Sessions are recorded but never yet an Agent one (no demo task or example sessions here; until the first
 *  session at all, the dashboard is the onboarding). */
export function SpotlightEmpty() {
  return (
    <Card variant="highlight">
      <CardContent className="flex flex-col gap-3">
        <Eyebrow />
        <div className="flex items-center gap-3"><Crumb pose="look" className="w-24 shrink-0" label="Empty state illustration" /><h3 className="text-lg font-semibold">No agent visits yet</h3></div>
        <p className="text-sm">When an AI agent visits your website, its session appears in Agent sessions.</p>
        <p className="text-xs text-muted-foreground">Human and Bot sessions are still recorded and stored. Key metrics includes both, and Deep dive includes Human sessions.</p>
      </CardContent>
    </Card>
  )
}
