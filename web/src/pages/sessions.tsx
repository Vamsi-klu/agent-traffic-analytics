// Sessions: everything by default, a pinned Agent filter, highlighted agent rows, muted bots (DESIGN.md §6.1).
// Data: /api/sessions, one page at a time; the filters live in the URL (like PostHog 1.0's event list). The verdict
// filter is All and the four verdicts; under Agent, a second row splits it into Agent only and Human + agent (named
// as src/lib/taxonomy.ts names them), which combines with the agent's name (the dashboard links to each name).
import { useState } from "react"
import { Pin } from "lucide-react"
import { useSearchParams } from "react-router"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { PageHeader } from "@/components/cake/bits"
import { Crumb } from "@/components/cake/crumb"
import { Loaded } from "@/components/cake/page-state"
import { SessionRow } from "@/components/cake/session-row"
import { Legend } from "@/components/cake/verdict"
import { api, asApiError, useApi } from "@/data/api"
import type { AgentTurns, DateRange, Evidence, SessionSummary, SessionsPage as Page, SessionsQuery, Verdict } from "@/data/types"
import { ALL, ANY_AGENT, RANGE_KEYS, VERDICT_FILTERS, choiceQuery, pick, readEvidence, readRange, readTurns } from "@/lib/filters"
import { TAXONOMY, TURNS_ORDER } from "@/lib/taxonomy"
import { RANGES, WORDS } from "@/lib/words"

/** The verdict chips after the pinned Agent one, in order. */
const CHIPS: { value: Verdict | typeof ALL; label: string }[] = [
  { value: ALL, label: "All" },
  { value: "human", label: TAXONOMY.verdicts.human.label },
  { value: "bot", label: TAXONOMY.verdicts.bot.label },
]

type Filters = { filter: Verdict | typeof ALL; turns: AgentTurns | typeof ALL; evidence: Evidence | typeof ALL; agent: string; range: DateRange }

export function SessionsPage() {
  const [params, setParams] = useSearchParams()
  const filter = pick(params.get("filter"), VERDICT_FILTERS, ALL)
  // the split only narrows Agent sessions and thin evidence Human ones, so each holds while its verdict is picked
  const agentPicked = filter === "agent", humanPicked = filter === "human"
  const filters: Filters = {
    filter, turns: agentPicked ? readTurns(params) : ALL, evidence: humanPicked ? readEvidence(params) : ALL,
    agent: params.get("agent") ?? ANY_AGENT, range: readRange(params),
  }
  const query: SessionsQuery = {
    verdict: choiceQuery(filters.filter),
    turns: choiceQuery(filters.turns),
    evidence: choiceQuery(filters.evidence),
    agent: filters.agent === ANY_AGENT ? undefined : filters.agent,
    range: filters.range,
  }
  const key = JSON.stringify(query)
  // The answer remembers its query, so the rows, "Load more" and its cursor always belong together.
  const first = useApi(async (signal) => ({ key, query, page: await api.sessions(query, signal) }), [key])
  const set = (name: keyof Filters) => (value: string) => setParams((p) => { p.set(name, value); return p })
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Sessions" lead={WORDS.sessionsLead} />
      <Loaded state={first} what="sessions">
        {(answer) => <SessionList key={answer.key} query={answer.query} page={answer.page} filters={filters} set={set} clear={() => setParams({})} />}
      </Loaded>
    </div>
  )
}

function SessionList({ query, page, filters, set, clear }: {
  query: SessionsQuery; page: Page; filters: Filters; set: (name: keyof Filters) => (value: string) => void; clear: () => void
}) {
  const [more, setMore] = useState<SessionSummary[]>([])
  const [next, setNext] = useState(page.next)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rows = [...page.results, ...more]
  const total = page.total // the rows on screen, even while a new filter loads
  const left = total - rows.length
  const loadMore = async (cursor: string) => {
    setLoading(true)
    try {
      const nextPage = await api.sessions({ ...query, cursor })
      setMore((m) => [...m, ...nextPage.results])
      setNext(nextPage.next)
      setError(null)
    } catch (e) {
      setError(asApiError(e).message)
    } finally {
      setLoading(false)
    }
  }
  return (
    <>
      <Card variant="flat" size="sm">
        <CardContent className="flex flex-wrap items-center gap-2">
          <ToggleGroup type="single" value={filters.filter} onValueChange={(v) => v && set("filter")(v)} aria-label="Verdict" className="flex-wrap">
            <ToggleGroupItem value="agent" variant="highlight" title={WORDS.pinnedFilter}><Pin aria-hidden />{TAXONOMY.verdicts.agent.label} <span className="font-mono text-xs">{page.counts.agent}</span></ToggleGroupItem>
            {CHIPS.map((c) => <ToggleGroupItem key={c.value} value={c.value} variant="outline">{c.label} <span className="font-mono text-xs">{page.counts[c.value]}</span></ToggleGroupItem>)}
          </ToggleGroup>
          <Separator orientation="vertical" className="h-6 max-md:hidden" />
          <Select value={filters.agent} onValueChange={set("agent")}><SelectTrigger aria-label="Agent"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value={ANY_AGENT}>Any agent</SelectItem>{page.agent_names.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}</SelectContent></Select>
          <Select value={filters.range} onValueChange={set("range")}><SelectTrigger aria-label="Date"><SelectValue /></SelectTrigger>
            <SelectContent>{RANGE_KEYS.map((r) => <SelectItem key={r} value={r}>{RANGES[r]}</SelectItem>)}</SelectContent></Select>
          {filters.filter === "agent" && (
            <ToggleGroup type="single" variant="outline" size="sm" value={filters.turns} onValueChange={(v) => v && set("turns")(v)} aria-label="Human involvement" className="basis-full flex-wrap">
              <ToggleGroupItem value={ALL}>{WORDS.eitherTurns} <span className="font-mono text-xs">{page.counts.agent}</span></ToggleGroupItem>
              {TURNS_ORDER.map((t) => <ToggleGroupItem key={t} value={t} title={TAXONOMY.turns[t].about}>{TAXONOMY.turns[t].label} <span className="font-mono text-xs">{page.counts[t]}</span></ToggleGroupItem>)}
            </ToggleGroup>
          )}
          {filters.filter === "human" && (
            <ToggleGroup type="single" variant="outline" size="sm" value={filters.evidence} onValueChange={(v) => v && set("evidence")(v)} aria-label="Evidence" className="basis-full flex-wrap">
              <ToggleGroupItem value={ALL}>{WORDS.allHumanSessions} <span className="font-mono text-xs">{page.counts.human}</span></ToggleGroupItem>
              <ToggleGroupItem value="thin" title={TAXONOMY.evidence.thin.about}>{TAXONOMY.evidence.thin.label} <span className="font-mono text-xs">{page.counts.thin}</span></ToggleGroupItem>
            </ToggleGroup>
          )}
        </CardContent>
      </Card>
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm text-muted-foreground">{total} sessions · newest first</span><Legend /></div>
      {rows.length ? (
        <div className="flex flex-col gap-3">{rows.map((s) => <SessionRow key={s.id} s={s} />)}</div>
      ) : (
        <Card variant="sunk"><CardContent className="flex flex-col items-center gap-3 py-6 text-center">
          <Crumb pose="sleep" className="w-32" title="Crumb is asleep: nothing matches." />
          <h3 className="text-lg font-semibold">No matches</h3>
          <p className="text-sm text-muted-foreground">Try a wider date range or clear the agent filter.</p>
          <Button variant="outline" size="sm" onClick={clear}>Clear filters</Button>
        </CardContent></Card>
      )}
      {error && <Alert variant="destructive"><AlertDescription>Couldn't load more sessions. {error} Try again.</AlertDescription></Alert>}
      {next && (
        <div className="flex justify-center">
          <Button variant="outline" disabled={loading} onClick={() => void loadMore(next)}>{`Load ${left > 0 ? Math.min(page.page_size, left) : page.page_size} more`}</Button>
        </div>
      )}
    </>
  )
}
