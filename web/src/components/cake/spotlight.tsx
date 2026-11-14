// The Agent block at the top of the dashboard (DESIGN.md §6.1), and its "none yet" version.
import { Play, TrendingDown, TrendingUp } from "lucide-react"
import { Link } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { Overview } from "@/data/types"
import { percent } from "@/lib/format"
import { TAXONOMY, TURNS_ORDER, UNNAMED } from "@/lib/taxonomy"
import { WORDS } from "@/lib/words"
import { AgentAvatar } from "./avatar"
import { Crumb, CrumbHead } from "./crumb"
import { SessionRow } from "./session-row"
import { Legend, TURNS_ICON } from "./verdict"

function Eyebrow() {
  return <span className="flex items-center gap-2 text-sm font-extrabold text-agent-foreground"><CrumbHead className="size-7" />{WORDS.agentSessions}</span>
}

/** The top of /api/overview: Agent counts, the change since last week, the split, each agent by name (listed by
 *  name, Unnamed together), and the newest three. */
export function Spotlight({ overview }: { overview: Overview }) {
  const { counts, latest_agent: latest } = overview
  const delta = counts.agent - overview.agent_last_week
  const Trend = delta < 0 ? TrendingDown : TrendingUp
  return (
    <Card variant="highlight" aria-labelledby="spot-title">
      <CardContent className="grid gap-5 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="flex flex-col gap-3">
          <Eyebrow />
          <div className="flex flex-wrap items-end gap-3">
            <span className="font-heading text-6xl leading-none font-semibold">{counts.agent}</span>
            <Badge variant="tag" className="mb-1"><Trend aria-hidden />{delta < 0 ? "−" : "+"}{Math.abs(delta)} versus last week</Badge>
          </div>
          <h2 id="spot-title" className="text-lg font-semibold">{WORDS.actedForHuman}</h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {TURNS_ORDER.map((turns) => {
              const Icon = TURNS_ICON[turns]
              return (
                <Link key={turns} to={`/sessions?filter=agent&turns=${turns}`} title={TAXONOMY.turns[turns].about} className="flex items-center gap-x-2 hover:underline">
                  <Icon className="size-4 shrink-0 text-agent-foreground" aria-hidden /><b>{counts[turns]}</b><span className="font-bold">{TAXONOMY.turns[turns].label}</span>
                </Link>
              )
            })}
          </div>
          <ul aria-label={WORDS.agentsByName} className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            {overview.agents_seen.map(({ name, sessions }) => (
              <li key={name ?? UNNAMED}>
                {name ? (
                  <Link to={`/sessions?filter=agent&agent=${encodeURIComponent(name)}`} className="flex items-center gap-x-1.5 hover:underline">
                    <AgentAvatar name={name} className="size-5" /><b>{sessions}</b><span className="font-bold">{name}</span>
                  </Link>
                ) : (
                  <span className="flex items-center gap-x-1.5" title={TAXONOMY.names.unnamed.about}><b>{sessions}</b><span className="font-bold text-muted-foreground">{UNNAMED}</span></span>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild><Link to="/sessions?filter=agent"><Play aria-hidden />Watch them</Link></Button>
            <span className="text-xs text-muted-foreground">{`${percent(counts.agent, counts.all)}% of all sessions`}</span>
          </div>
        </div>
        <Card variant="flat" size="sm">
          <CardContent className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2"><b className="text-sm">Latest</b><Legend /></div>
            {latest.length ? latest.map((s) => <SessionRow key={s.id} s={s} compact />) : <p className="text-sm text-muted-foreground">No sessions match these filters.</p>}
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
        <div className="flex items-center gap-3"><Crumb pose="look" className="w-24 shrink-0" title="Crumb is waiting for an agent" /><h2 className="text-lg font-semibold">No agent has visited yet</h2></div>
        <p className="text-sm">When an AI agent visits your website, its session shows up here first.</p>
        <p className="text-xs text-muted-foreground">Human and Bot sessions are still recorded and kept. The rest of the dashboard shows them.</p>
      </CardContent>
    </Card>
  )
}
