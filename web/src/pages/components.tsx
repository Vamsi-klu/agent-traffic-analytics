// Component overview: every component and every variant cake uses, like the shadcn docs.
// This page is in the visual baseline: any change to a component shows up here first (DESIGN.md §12).
// Components that draw data show cake's own (/api/overview and /api/register); the rest show fixed sample props.
import type { ReactNode } from "react"
import { ChevronDown, Copy, Download, MoreHorizontal, Play, Plus, Trash2 } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { BudgetWarning, CopyBlock, PageHeader, StatCard, StorageMeter, StorageUse } from "@/components/cake/bits"
import { Crumb, CrumbHead } from "@/components/cake/crumb"
import { OnboardingStep, OrSeparator } from "@/components/cake/onboarding"
import { ProjectLink } from "@/components/cake/project-link"
import { Loaded, PageError, PageLoading } from "@/components/cake/page-state"
import { SessionRow } from "@/components/cake/session-row"
import { Spotlight, SpotlightEmpty } from "@/components/cake/spotlight"
import { MiniTimeline, SessionTimeline, segsInTimeOrder, spansOf, timeLabel, timelineView } from "@/components/cake/timeline"
import { ReplayControls, ReplayStage } from "@/components/cake/replay-stage"
import { ReasonLayer } from "@/components/cake/reasons"
import { ServerHalfTable } from "@/components/cake/server-half"
import { SessionPages } from "@/components/cake/session-pages"
import { Legend, Swatch, ThinEvidenceTag, TurnsBadge, UnnamedTag, VERDICTS, VerdictBadge } from "@/components/cake/verdict"
import { AVATAR_SHAPES, AgentAvatar, AgentTag } from "@/components/cake/avatar"
import { BotHelp, Coverage, Taxonomy } from "@/components/cake/coverage"
import { PagesTable } from "@/components/cake/pages-table"
import { RegisterCard } from "@/components/cake/register-card"
import { UNREACHABLE, api, useApi } from "@/data/api"
import type { LayerReasons, Overview, Registration, ServerHalf, SessionPage, SessionSummary } from "@/data/types"
import { mbToBytes } from "@/lib/format"
import type { ReplayState } from "@/lib/use-replay"
import { PRODUCT_NAME } from "@/lib/product"
import { WORDS } from "@/lib/words"

function Block({ name, use, children }: { name: string; use: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-t-2 border-dashed border-border pt-6">
      <div className="flex flex-col gap-0.5"><h2 className="font-mono text-base font-bold">{name}</h2><p className="text-sm text-muted-foreground">{use}</p></div>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  )
}

const chartConfig = {
  human: { label: VERDICTS.human.label, color: "var(--chart-1)" },
  agent: { label: VERDICTS.agent.label, color: "var(--chart-2)" },
  unsure: { label: VERDICTS.unknown.label, color: "var(--chart-3)" },
} satisfies ChartConfig

/** One SessionRow per look: highlighted (Agent: Human + agent, Agent only), normal (Human, Human on thin evidence),
 *  muted (Bot). */
const ROW_LOOKS: ((s: SessionSummary) => boolean)[] = [
  (s) => s.agent_turns === "human_agent", (s) => s.agent_turns === "agent_only", (s) => s.verdict === "human",
  (s) => s.evidence === "thin", (s) => s.verdict === "bot",
]

/** A layer for each look: a verdict with its reasons, and a layer that is off with no reason given. */
const LAYER_LOOKS: LayerReasons[] = [
  { layer: "environment", state: "agent", leans: "agent", percent: 99, reasons: [{ kind: "page", tone: "agent", text: "Automation software controls this browser.", detail: "navigator.webdriver is true" }, { kind: "browser", tone: "none", text: "Real GPU, normal screen.", detail: null }] },
  { layer: "verify", state: "off", leans: null, percent: null, reasons: [] },
]
/** A server half with each kind of row: a plain page request, and a signed one from another network. */
const SERVER_LOOKS: ServerHalf = {
  pages: [
    { at_ms: 0, path: "/", fetch: { site: "none", mode: "navigate", dest: "document", user: "?1" }, signature: null, same_network: true, same_user_agent: true, same_language: true, reuses: 0 },
    { at_ms: 41250, path: "/pricing", fetch: { site: "same-origin", mode: "navigate", dest: "document", user: null }, signature: { agent: "chatgpt.com", verified: true }, same_network: false, same_user_agent: true, same_language: null, reuses: 1 },
  ],
  network: { country: "US", range: "OpenAI ChatGPT agent", ja4: "t13d1516h2_8daaf6152771", protocol: "HTTP/2" },
  note: null,
}
/** Pages of each look: who acted on them (a human, both, an agent only) and a page without actions. */
const PAGE_LOOKS: SessionPage[] = [
  { path: "/", at_ms: 0, duration_ms: 21300, actions: 3, who: "human" },
  { path: "/pricing?plan=team", at_ms: 21300, duration_ms: 44700, actions: 7, who: "human_agent" },
  { path: "/signup", at_ms: 66000, duration_ms: 4000, actions: 0, who: "agent" },
]
const nothing = () => undefined
/** The replay stage and its controls as they look with no player behind them (the session page plays for real). */
const EXAMPLE_SITE = "https://shop.example.com/"

function stillReplay(address: string, status: ReplayState["status"]): ReplayState {
  return { status, missing: "freed", error: null, timeMs: 52000, playing: false, waiting: false, noPage: false, speed: 1, address, mount: nothing,
    play: nothing, pause: nothing, seek: nothing, setSpeed: nothing, jumpTo: nothing, nextHandoff: 80000, jumpToHandoff: nothing, retry: nothing }
}

export function ComponentsPage() {
  const data = useApi((signal) => Promise.all([api.overview({}, signal), api.registration(signal)]), [])
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Components" lead={`Every component and variant ${PRODUCT_NAME} uses. New look = new variant here + DESIGN.md, never a one-off on a page.`} />
      <Loaded state={data} what="the component overview">{([overview, registration]) => <Overview overview={overview} registration={registration} />}</Loaded>
    </div>
  )
}

function Overview({ overview: o, registration }: { overview: Overview; registration: Registration }) {
  const rows = ROW_LOOKS.flatMap((look) => o.latest.find(look) ?? [])
  const mixed = rows.find((s) => s.agent_turns === "human_agent")
  const mixedSpans = mixed?.segments && spansOf(mixed.segments, mixed.duration_ms)
  return (
    <>
      <Block name="Button · variant" use="default = the one main action per screen · outline = secondary · secondary = soft secondary · ghost = toolbars, nav · destructive = delete · link = inline">
        <Button>Default</Button><Button variant="outline">Outline</Button><Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button><Button variant="destructive"><Trash2 aria-hidden />Destructive</Button><Button variant="link">Link</Button>
      </Block>
      <Block name="Button · size" use="lg = hero only · default · sm = inside cards and rows · icon sizes always with a Tooltip">
        <Button size="lg"><Play aria-hidden />Large</Button><Button>Default</Button><Button size="sm">Small</Button><Button size="xs">Extra small</Button>
        {([["icon-lg", "Add"], ["icon", "Copy"], ["icon-sm", "Download"]] as const).map(([size, label]) => (
          <Tooltip key={size}>
            <TooltipTrigger asChild><Button variant="outline" size={size} aria-label={label}>{label === "Add" ? <Plus /> : label === "Copy" ? <Copy /> : <Download />}</Button></TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        ))}
      </Block>

      <Block name="Badge · verdicts (VerdictBadge) · ThinEvidenceTag" use="the only way to show a verdict: icon + word + colour · Unknown only for a stretch, an action or a layer that couldn't tell · thin evidence beside a Human badge cake couldn't tell">
        <VerdictBadge verdict="human" /><VerdictBadge verdict="agent" /><VerdictBadge verdict="bot" /><VerdictBadge verdict="unknown" /><ThinEvidenceTag />
      </Block>
      <Block name="VerdictBadge · TurnsBadge · percent" use="the session page: how sure cake is of the verdict and of each layer, bold on the highlighter · a Human verdict on thin evidence shows its own, lower chance beside the mark">
        <VerdictBadge verdict="agent" percent={94} /><VerdictBadge verdict="human" percent={96} /><VerdictBadge verdict="human" percent={55} /><ThinEvidenceTag />
        <VerdictBadge verdict="bot" percent={99} /><TurnsBadge turns="human_agent" percent={97} />
      </Block>
      <Block name="TurnsBadge · AgentTag · UnnamedTag" use="inside Agent: Agent only or Human + agent (half human, half agent) · which agent: its name with how sure the name is inside the same tag (rows and the session page alike), or Unnamed">
        <TurnsBadge turns="agent_only" /><TurnsBadge turns="human_agent" /><AgentTag name="Playwright" />
        <AgentTag name="ChatGPT agent" certainty="verified" /><AgentTag name="Claude in Chrome" certainty="likely" /><AgentTag name="Comet" certainty="possible" /><UnnamedTag />
      </Block>
      <Block name="Badge · variant" use="tag = neutral facts (agent name, source, “example data”) · default/secondary/outline/destructive from shadcn">
        <Badge variant="tag">Claude in Chrome</Badge><Badge variant="tag">example data</Badge><Badge>Default</Badge><Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge><Badge variant="destructive">Destructive</Badge>
      </Block>
      <Block name="Legend · Swatch" use="always next to a share bar, timeline or chart with 2+ series">
        <Legend /><Swatch kind="mixed" />
      </Block>

      <Block name="Card · variant" use="default = framed content · flat = plain numbers · sunk = empty states, previews · highlight = Agent only">
        <div className="grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {(["default", "flat", "sunk", "highlight"] as const).map((v) => (
            <Card key={v} variant={v} size="sm"><CardHeader><CardTitle>{v}</CardTitle><CardDescription>Card variant="{v}"</CardDescription></CardHeader></Card>
          ))}
        </div>
      </Block>
      <Block name="StatCard" use="regular numbers under the highlight block; muted for bots">
        <div className="grid w-full gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label={VERDICTS.human.label} value={String(o.counts.human)} sub="the comparison group" mark={<Swatch kind="h" />} />
          <StatCard label={VERDICTS.bot.label} value={String(o.counts.bot)} sub="counted, not highlighted" mark={<Swatch kind="u" />} muted help={<BotHelp bot={o.coverage.bot} />} />
        </div>
      </Block>

      <Block name="Spotlight" use="dashboard top: sessions where an agent acted for a human"><div className="w-full"><Spotlight overview={o} /></div></Block>
      <Block name="Spotlight · none yet" use="sessions are recorded, but never yet a human + agent one"><div className="w-full"><SpotlightEmpty /></div></Block>

      <Block name="SessionRow" use="highlighted (Agent: Human + agent, Agent only) · normal (Human, Unknown) · muted (Bot) · compact">
        <div className="flex w-full flex-col gap-3">
          {rows.map((s) => <SessionRow key={s.id} s={s} />)}
          {rows[0] && <div className="max-w-sm"><SessionRow s={rows[0]} compact /></div>}
        </div>
      </Block>
      <Block name="MiniTimeline · SessionTimeline" use="a row's timeline: each stretch at its place, read aloud by time · the session page's share of actions, in the order who acts first · hand-off labels (two close ones take two rows, so neither covers the other); playhead">
        <div className="flex w-full flex-col gap-4">
          {mixed?.segments && <MiniTimeline spans={mixedSpans} label={timeLabel(mixed.segments)} />}
          {mixed?.segments && <MiniTimeline human={35} agent={65} unsure={0} segs={segsInTimeOrder(mixed.segments, { human: 35, agent: 65, unsure: 0 })} size="lg" />}
          {mixed?.segments && (
            <SessionTimeline {...timelineView({ duration_ms: mixed.duration_ms, segments: mixed.segments,
              handoffs: [{ at_ms: 38_000, to: "agent" }, { at_ms: 83_000, to: "human" }] }, { playheadMs: mixed.duration_ms / 2 })} />
          )}
          <SessionTimeline {...timelineView({ duration_ms: 215_000,
            segments: [{ who: "human", start_ms: 0, end_ms: 4_000 }, { who: "agent", start_ms: 39_000, end_ms: 78_000 }, { who: "human", start_ms: 78_000, end_ms: 215_000 }],
            handoffs: [{ at_ms: 39_000, to: "agent" }, { at_ms: 78_000, to: "human" }] })} />
        </div>
      </Block>
      <Block name="Table" use="framed by a Card; numbers right-aligned">
        <Card className="w-full py-0">
          <Table>
            <TableHeader><TableRow><TableHead>Page</TableHead><TableHead className="text-right">Agent visits</TableHead><TableHead>Human / agent</TableHead></TableRow></TableHeader>
            <TableBody><TableRow><TableCell className="font-mono">/cart</TableCell><TableCell className="text-right">22</TableCell><TableCell><MiniTimeline human={29} agent={71} unsure={0} /></TableCell></TableRow></TableBody>
          </Table>
        </Card>
      </Block>

      <Block name="Tabs · ToggleGroup · Select" use="Tabs = switch panels · ToggleGroup = pick one value (language, speed, retention) · Select = filters">
        <Tabs defaultValue="a"><TabsList><TabsTrigger value="a">On this computer</TabsTrigger><TabsTrigger value="b">On a server</TabsTrigger></TabsList><TabsContent value="a" /></Tabs>
        <ToggleGroup type="single" variant="outline" defaultValue="30"><ToggleGroupItem value="all">Keep everything</ToggleGroupItem><ToggleGroupItem value="30">30 days</ToggleGroupItem></ToggleGroup>
        <Select defaultValue="any"><SelectTrigger aria-label="Agent"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="any">Any agent</SelectItem><SelectItem value="cic">Claude in Chrome</SelectItem></SelectContent></Select>
      </Block>
      <Block name="Input · Label · Switch · Checkbox" use="Switch = on/off settings · Checkbox = a yes the owner gives on a form (product updates on the registration card), never ticked for them; label always visible">
        <div className="flex w-64 flex-col gap-1.5"><Label htmlFor="sel">Hide these parts of the page</Label><Input id="sel" defaultValue=".account-email" /></div>
        <Switch defaultChecked aria-label="On" /><Switch aria-label="Off" /><Switch size="sm" defaultChecked aria-label="Small" />
        <div className="flex items-center gap-2"><Checkbox id="box-off" /><Label htmlFor="box-off">Not ticked</Label></div>
        <div className="flex items-center gap-2"><Checkbox id="box-on" defaultChecked /><Label htmlFor="box-on">Ticked</Label></div>
      </Block>
      <Block name="Progress · StorageMeter · StorageUse · BudgetWarning" use="tone ok below 80%, warn from 80%; dashed line at 80% · StorageUse = the bar + what is used of the budget and when it is full (settings, the dashboard's Disk) · BudgetWarning = from 80%, how full and what happens when full; once full and nothing can be freed, that new replays aren't stored">
        <div className="flex w-full max-w-md flex-col gap-4"><StorageMeter usedPct={31} warnAtPct={80} /><StorageMeter usedPct={82} warnAtPct={80} /></div>
        <div className="flex w-full max-w-md flex-col gap-3"><StorageUse usedBytes={o.storage.used_bytes} budgetBytes={mbToBytes(o.storage.budget_mb)} warnAtPct={o.storage.warn_at_pct} daysLeft={o.storage.days_left} disk={o.storage.disk} replaysStopped={o.storage.replays_stopped} /></div>
        <div className="grid w-full gap-3 md:grid-cols-2"><BudgetWarning usedPct={84} warnAtPct={80} autoFree full={false} /><BudgetWarning usedPct={100} warnAtPct={80} autoFree={false} full /></div>
      </Block>
      <Block name="Alert · variant" use="info = explanations · warn = needs attention (80% disk) · ok = done · destructive = failed">
        <div className="grid w-full gap-3 md:grid-cols-2">
          <Alert variant="info"><AlertTitle>{VERDICTS.agent.label}</AlertTitle><AlertDescription>The behavior changes twice.</AlertDescription></Alert>
          <Alert variant="warn"><AlertTitle>The disk budget is 82% full</AlertTitle><AlertDescription>8.2 of 10 GB. Raise the budget or let {PRODUCT_NAME} free space.</AlertDescription></Alert>
          <Alert variant="ok"><AlertTitle>Receiving visits</AlertTitle><AlertDescription>Your site sent a visit 2 minutes ago.</AlertDescription></Alert>
          <Alert variant="destructive"><AlertTitle>Can't reach the server half</AlertTitle><AlertDescription>Check the signing key in Settings.</AlertDescription></Alert>
        </div>
      </Block>
      <Block name="Dialog · DropdownMenu · Tooltip" use="Dialog = confirm destructive actions · DropdownMenu = row actions · Tooltip = every icon-only button">
        <Dialog>
          <DialogTrigger asChild><Button variant="destructive"><Trash2 aria-hidden />Delete all data</Button></DialogTrigger>
          <DialogContent><DialogHeader><DialogTitle>Delete every session?</DialogTitle><DialogDescription>This removes 150 sessions and their replays from this computer. It can't be undone.</DialogDescription></DialogHeader>
            <DialogFooter><Button variant="outline">Cancel</Button><Button variant="destructive">Delete</Button></DialogFooter></DialogContent>
        </Dialog>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="outline">Actions<ChevronDown aria-hidden /></Button></DropdownMenuTrigger>
          <DropdownMenuContent><DropdownMenuItem>Watch replay</DropdownMenuItem><DropdownMenuItem>Copy session link</DropdownMenuItem></DropdownMenuContent>
        </DropdownMenu>
        <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" aria-label="More"><MoreHorizontal /></Button></TooltipTrigger><TooltipContent>More</TooltipContent></Tooltip>
      </Block>
      <Block name="Chart (shadcn Chart + recharts)" use="chart-1 human · chart-2 agent · chart-3 not sure; one axis; legend; tooltip; table view">
        <Card className="w-full max-w-xl"><CardContent>
          <ChartContainer config={chartConfig} className="aspect-auto h-40 w-full">
            <AreaChart data={o.share_by_day} margin={{ left: 0, right: 8 }}>
              <CartesianGrid vertical={false} /><XAxis dataKey="day" tickLine={false} axisLine={false} /><YAxis width={46} tickLine={false} axisLine={false} unit="%" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Area dataKey="agent" stackId="1" type="monotone" fill="var(--color-agent)" stroke="var(--color-agent)" fillOpacity={1} />
              <Area dataKey="unsure" stackId="1" type="monotone" fill="var(--color-unsure)" stroke="var(--color-unsure)" fillOpacity={0.35} />
              <Area dataKey="human" stackId="1" type="monotone" fill="var(--color-human)" stroke="var(--color-human)" fillOpacity={1} />
            </AreaChart>
          </ChartContainer>
        </CardContent></Card>
      </Block>
      <Block name="CopyBlock · OrSeparator" use="commands and the one sentence for a coding agent; placeholders only">
        <div className="flex w-full max-w-xl flex-col gap-3"><CopyBlock text="agentcake setup --print --site" /><OrSeparator /></div>
      </Block>
      <Block name="OnboardingStep" use="one numbered step of connecting the website (home page and dashboard before the first visit)">
        <div className="w-full max-w-xl"><OnboardingStep n={1} title="Your website's address"><p className="text-sm text-muted-foreground">What to do in this step.</p></OnboardingStep></div>
      </Block>
      <Block name="ProjectLink" use="the top bar's project: the website's address, opened in a new tab · until it is set, a link to Settings">
        <div className="flex flex-wrap items-center gap-2"><ProjectLink domain="shop.example.com" /><ProjectLink domain={null} /></div>
      </Block>
      <Block name="Crumb" use="wave (welcome, moves) · look (waiting) · sleep (no results) · oops (errors) · head (logo, human + agent marker)">
        {(["wave", "look", "sleep", "oops"] as const).map((p) => <Crumb key={p} pose={p} className="w-28" title={`Crumb, ${p}`} />)}
        <CrumbHead className="size-12" /><CrumbHead className="size-6" />
      </Block>
      <Separator />
      <Block name="AgentAvatar · AgentTag" use="one fixed dessert-blob per agent, name always next to it · flat colour from --avatar-1..6, never a verdict colour · idles and blinks, still with reduced motion">
        <div className="flex w-full flex-col gap-4">
          <div className="flex flex-wrap items-end gap-4">
            {AVATAR_SHAPES.map((shape, i) => (
              <span key={shape} className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
                <AgentAvatar look={{ shape: i, colour: 1 + (i % 6), phase: i % 6 }} className="size-14" />{shape}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">{o.agents_seen.flatMap((a) => (a.name ? [<AgentTag key={a.name} name={a.name} />] : []))}</div>
        </div>
      </Block>
      <Block name="Coverage · BotHelp" use="dashboard bottom: each kind of visit it records, how it's shown and how it's decided · wording from /api/overview · BotHelp = the Bots number’s “?”">
        <div className="w-full"><Coverage coverage={o.coverage} /></div>
      </Block>
      <Block name="Taxonomy" use="dashboard bottom, after Coverage: the session categories level by level, each with its badge or tag and a sentence · words from judging.en.json, read when the pages are built">
        <div className="w-full"><Taxonomy /></div>
      </Block>
      <Block name="PagesTable" use="top pages, one component for both lists: by agent visits and by human visits · same columns and widths, numbers from the same data">
        <div className="w-full"><PagesTable title={WORDS.pagesHumans} by="human" pages={o.top_pages} /></div>
      </Block>
      <Block name="PageLoading · PageError" use="before a page's data is there: loading (fades in only when it takes a moment) · can't load (what happened, Try again) · Loaded picks between them and the page">
        <div className="grid w-full items-center gap-4 md:grid-cols-2">
          <PageLoading what="sessions" />
          <PageError title="Couldn't load sessions" message={UNREACHABLE} onRetry={() => undefined} />
        </div>
      </Block>
      <Block name="ReplayStage · ReplayControls" use="the replay window: rrweb-player on the stage, cursor labelled with who acts · what it says with no replay · play, time, speed, Jump to hand-off">
        <Card className="w-full max-w-xl gap-0 py-0">
          <ReplayStage replay={stillReplay(EXAMPLE_SITE, "missing")} />
          <ReplayControls replay={stillReplay(EXAMPLE_SITE, "ready")} durationMs={96400} />
        </Card>
      </Block>
      <Block name="SessionPages" use="pages in the replay, in the order they opened: entry and exit page, opening time, time on page, who acted there, and their actions · selecting a row moves the replay to that page and plays it">
        <div className="w-full max-w-xl"><SessionPages pages={PAGE_LOOKS} onJump={nothing} /></div>
      </Block>
      <Block name="ReasonLayer" use="one of the four layers of Why this verdict · each reason says what it means, with what was seen under it in smaller type · a layer that is off is dashed and still says why">
        <div className="grid w-full items-start gap-3 md:grid-cols-2">{LAYER_LOOKS.map((layer) => <ReasonLayer key={layer.layer} layer={layer} />)}</div>
      </Block>
      <Block name="ServerHalfTable" use="Server half: what the site's server saw of each page request; the network line in server mode">
        <div className="w-full"><ServerHalfTable server={SERVER_LOOKS} /></div>
      </Block>
      <Block name="RegisterCard" use="before every page until this AgentCake has registered: its words are in src/lib/registration.ts, See what is sent = the exact JSON, the button off until the email passes cake's check · shown here after a press that couldn't be sent: why, then Continue (no retry; it asks again next time)">
        <div className="w-full">
          <RegisterCard rules={registration} outcome={{ state: "not_sent", message: "Couldn't reach tartini.ai ([Errno 8] nodename nor servname provided, or not known), so your registration wasn't sent." }}
            onRegister={nothing} onContinue={nothing} initial={{ email: "owner@example.com", company: "Example Shop" }} />
        </div>
      </Block>

    </>
  )
}
