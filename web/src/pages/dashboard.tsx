// Dashboard: the Agent block first, then regular numbers, how long sessions last (D30), charts, pages, all latest
// sessions, the disk, what cake records and the session categories (DESIGN.md §1.1, D39). One AgentCake is one
// project, its website (D40): no source filter. Until the first session it shows how to connect the website, the home
// page's onboarding (D37, as PostHog 1.0's dashboard showed its setup over the page until the first event). Data:
// /api/setup (is anything recorded, and was there ever an Agent session), then /api/overview filtered by date range
// (kept in the URL, like PostHog 1.0's filters).
import { useState, type ReactNode } from "react"
import { Activity, Bot, Clock } from "lucide-react"
import { Link, useSearchParams } from "react-router"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { BudgetWarning, PageHeader, SectionTitle, StatCard, StorageUse, Columns } from "@/components/cake/bits"
import { SessionRow } from "@/components/cake/session-row"
import { Spotlight, SpotlightEmpty } from "@/components/cake/spotlight"
import { PagesTable } from "@/components/cake/pages-table"
import { Legend, Swatch, TURNS_ICON, VERDICTS } from "@/components/cake/verdict"
import { AgentTick } from "@/components/cake/avatar"
import { BotHelp, Coverage, Taxonomy } from "@/components/cake/coverage"
import { Loaded } from "@/components/cake/page-state"
import { api, useApi } from "@/data/api"
import type { DateRange, Overview, Storage } from "@/data/types"
import { RANGE_KEYS, readRange } from "@/lib/filters"
import { duration, mbToBytes, percent } from "@/lib/format"
import { TAXONOMY, UNNAMED } from "@/lib/taxonomy"
import { RANGES, WORDS } from "@/lib/words"
import { Onboarding } from "@/pages/home"

const shareConfig = {
  human: { label: VERDICTS.human.label, color: "var(--chart-1)" },
  agent: { label: VERDICTS.agent.label, color: "var(--chart-2)" },
  unsure: { label: VERDICTS.unknown.label, color: "var(--chart-3)" },
} satisfies ChartConfig
const agentConfig = { sessions: { label: "Sessions", color: "var(--chart-2)" } } satisfies ChartConfig

export function Filters({ range, onRange }: { range: DateRange; onRange: (v: string) => void }) {
  return (
    <Select value={range} onValueChange={onRange}><SelectTrigger aria-label="Date range"><SelectValue /></SelectTrigger>
      <SelectContent>{RANGE_KEYS.map((r) => <SelectItem key={r} value={r}>{RANGES[r]}</SelectItem>)}</SelectContent></Select>
  )
}

export function DashboardPage() {
  const [asked, setAsked] = useState(0)
  const setup = useApi((signal) => api.setup(signal), [asked])
  return (
    <Loaded state={setup} what="the dashboard">
      {(s) => (s.recorded.sessions > 0 ? <Dashboard agentEver={s.recorded.agent > 0} />
        : <Onboarding setup={s} onOpen={() => setAsked(asked + 1)} />)}
    </Loaded>
  )
}

function Dashboard({ agentEver }: { agentEver: boolean }) {
  const [params, setParams] = useSearchParams()
  const range = readRange(params)
  const overview = useApi((signal) => api.overview({ range }, signal), [range])
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Dashboard" lead={WORDS.dashboardLead} actions={<Filters range={range} onRange={(value) => setParams((p) => { p.set("range", value); return p })} />} />
      <Loaded state={overview} what="the dashboard">{(o) => <DashboardBody o={o} agentEver={agentEver} />}</Loaded>
    </div>
  )
}

function DashboardBody({ o, agentEver }: { o: Overview; agentEver: boolean }) {
  const [table, setTable] = useState(false)
  const { counts, coverage } = o
  return (
    <>
      {counts.agent > 0 || agentEver ? <Spotlight overview={o} /> : <SpotlightEmpty />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard label="All sessions" value={String(counts.all)} sub="All recorded and kept" mark={<Activity className="size-4" aria-hidden />} />
        <StatCard label={VERDICTS.human.label} value={String(counts.human)} sub={counts.thin ? `${counts.thin} ${WORDS.withThinEvidence}` : WORDS.comparisonGroup} mark={<Swatch kind="h" />} />
        <StatCard label={VERDICTS.bot.label} value={String(counts.bot)} sub="Counted, not highlighted" mark={<Bot className="size-4" aria-hidden />} muted help={<BotHelp bot={coverage.bot} />} />
      </div>
      <AverageLength o={o} />
      <Columns ratio="3-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Clock className="size-5" aria-hidden />{WORDS.timeChart}</CardTitle>
            <CardDescription>{WORDS.timeChartLead}</CardDescription>
            <CardAction><Legend /></CardAction>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <ChartContainer config={shareConfig} className="aspect-auto h-56 w-full">
              <AreaChart data={o.share_by_day} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} />
                <YAxis width={46} tickLine={false} axisLine={false} unit="%" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area dataKey="agent" stackId="1" type="monotone" fill="var(--color-agent)" stroke="var(--color-agent)" fillOpacity={1} />
                <Area dataKey="unsure" stackId="1" type="monotone" fill="var(--color-unsure)" stroke="var(--color-unsure)" fillOpacity={0.35} />
                <Area dataKey="human" stackId="1" type="monotone" fill="var(--color-human)" stroke="var(--color-human)" fillOpacity={1} />
              </AreaChart>
            </ChartContainer>
            <div><Button variant="link" size="sm" onClick={() => setTable(!table)}>{table ? "Hide table" : "Show as table"}</Button></div>
            {table && (
              <Table>
                <TableHeader><TableRow><TableHead>Day</TableHead><TableHead className="text-right">{VERDICTS.human.label}</TableHead><TableHead className="text-right">{VERDICTS.agent.label}</TableHead><TableHead className="text-right">{VERDICTS.unknown.label}</TableHead></TableRow></TableHeader>
                <TableBody>{o.share_by_day.map((d) => <TableRow key={d.day}><TableCell>{d.day}</TableCell><TableCell className="text-right">{d.human}%</TableCell><TableCell className="text-right">{d.agent}%</TableCell><TableCell className="text-right">{d.unsure}%</TableCell></TableRow>)}</TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Bot className="size-5" aria-hidden />Agents that visited</CardTitle>
            <CardAction className="text-xs text-muted-foreground">Agent sessions, with or without a human</CardAction>
          </CardHeader>
          <CardContent>
            <ChartContainer config={agentConfig} className="aspect-auto h-56 w-full">
              <BarChart data={o.agents_seen.map((a) => ({ ...a, name: a.name ?? UNNAMED }))} layout="vertical" margin={{ left: 0, right: 28 }}>
                <XAxis type="number" hide /><YAxis type="category" dataKey="name" width={200} tickLine={false} axisLine={false} tick={<AgentTick />} />
                <ChartTooltip content={<ChartTooltipContent hideLabel={false} />} />
                <Bar dataKey="sessions" fill="var(--color-sessions)" radius={4}><LabelList dataKey="sessions" position="right" className="fill-foreground font-bold" /></Bar>
              </BarChart>
            </ChartContainer>
            <p className="mt-2 text-xs text-muted-foreground">Bots are counted separately and aren't in this chart.</p>
          </CardContent>
        </Card>
      </Columns>
      <Columns ratio="1-1">
        <PagesTable title={WORDS.pagesAgents} by="agent" pages={o.top_pages} />
        <PagesTable title={WORDS.pagesHumans} by="human" pages={o.top_pages} />
      </Columns>
      <div>
        <SectionTitle aside={<Button variant="link" size="sm" asChild><Link to="/sessions">See all {counts.all} sessions</Link></Button>}>Latest sessions of every kind</SectionTitle>
        <div className="flex flex-col gap-3">{o.latest.map((s) => <SessionRow key={s.id} s={s} />)}</div>
      </div>
      <Disk storage={o.storage} />
      <div>
        <SectionTitle>{coverage.title}</SectionTitle>
        <p className="-mt-1 mb-3 text-sm text-muted-foreground">{coverage.lead}</p>
        <Coverage coverage={coverage} />
      </div>
      <section aria-labelledby="categories-title">
        <h3 id="categories-title" className="mt-6 mb-1 text-lg font-semibold">{TAXONOMY.title}</h3>
        <p className="mb-3 text-sm text-muted-foreground">{TAXONOMY.lead}</p>
        <Taxonomy />
      </section>
    </>
  )
}

/** D30: how long sessions last, one cell per kind of visitor (a Human + agent session counts only under Human + agent). */
function AverageLength({ o }: { o: Overview }) {
  const { ms, about } = o.average_length
  const { agent_only: AgentOnlyIcon, human_agent: HumanAgentIcon } = TURNS_ICON
  const cell = (label: string, length: number | null, sub: string, mark: ReactNode) =>
    <StatCard key={label} label={label} value={length === null ? "—" : duration(length)} sub={length === null ? "No sessions in this range" : sub} mark={mark} />
  return (
    <section aria-label={WORDS.averageLength}>
      <SectionTitle>{WORDS.averageLength}</SectionTitle>
      <p className="-mt-1 mb-3 text-sm text-muted-foreground">{about}</p>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {cell(VERDICTS.human.label, ms.human, WORDS.comparisonGroup, <Swatch kind="h" />)}
        {cell(TAXONOMY.turns.agent_only.label, ms.agent_only, WORDS.agentWholeWay, <AgentOnlyIcon className="size-4 text-agent-foreground" aria-hidden />)}
        {cell(TAXONOMY.turns.human_agent.label, ms.human_agent, WORDS.takingTurns, <HumanAgentIcon className="size-4 text-agent-foreground" aria-hidden />)}
      </div>
    </section>
  )
}

/** The disk budget, as the settings page shows it, with a warning from warn_at_pct (DESIGN.md §1.1, like 0.3.4's). */
function Disk({ storage }: { storage: Storage }) {
  const budget = mbToBytes(storage.budget_mb), usedPct = percent(storage.used_bytes, budget)
  return (
    <section aria-label="Disk">
      <SectionTitle aside={<Button variant="link" size="sm" asChild><Link to="/settings">Settings</Link></Button>}>Disk</SectionTitle>
      <Card variant="flat" size="sm">
        <CardContent className="flex flex-col gap-3">
          <StorageUse usedBytes={storage.used_bytes} budgetBytes={budget} warnAtPct={storage.warn_at_pct} daysLeft={storage.days_left}
            disk={storage.disk} replaysStopped={storage.replays_stopped} />
          <BudgetWarning usedPct={usedPct} warnAtPct={storage.warn_at_pct} autoFree={storage.auto_free} full={storage.replays_stopped === "budget"} />
        </CardContent>
      </Card>
    </section>
  )
}
