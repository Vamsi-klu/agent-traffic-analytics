// One session: replay + who acted when + pages visited + four-layer reasons + server half + every action (DESIGN.md §6). Data:
// /api/session/<id>; the replay plays in rrweb-player, chunk by chunk from …/replay?chunk=<n> (lib/use-replay.ts).
import { ArrowLeft, Search, Sparkles, Timer } from "lucide-react"
import { Link, useParams } from "react-router"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { SectionTitle, Columns } from "@/components/cake/bits"
import { AgentTag } from "@/components/cake/avatar"
import { Loaded } from "@/components/cake/page-state"
import { ReplayControls, ReplayStage, missingText } from "@/components/cake/replay-stage"
import { ServerHalfTable } from "@/components/cake/server-half"
import { SessionPages } from "@/components/cake/session-pages"
import { MiniTimeline, SessionTimeline, segsInTimeOrder, timelineView } from "@/components/cake/timeline"
import { Legend, ThinEvidenceTag, TurnsBadge, UnnamedTag, VERDICTS, VerdictBadge } from "@/components/cake/verdict"
import { ReasonLayer } from "@/components/cake/reasons"
import { api, useApi } from "@/data/api"
import type { Actor, SessionDetail } from "@/data/types"
import { clock, duration } from "@/lib/format"
import { actorAt } from "@/lib/replay-timing"
import { useReplay, type ReplayState } from "@/lib/use-replay"
import { WORDS } from "@/lib/words"

export function SessionPage() {
  const { id = "" } = useParams()
  const detail = useApi((signal) => api.session(id, signal), [id])
  return (
    <div className="flex flex-col gap-5">
      <div><Button variant="link" size="sm" asChild><Link to="/sessions"><ArrowLeft aria-hidden />{WORDS.sessionsPage}</Link></Button></div>
      <Loaded state={detail} what="this session">{(d) => <SessionBody key={d.session.id} d={d} />}</Loaded>
    </div>
  )
}

/** The cursor's name for each actor: the agent by name, a human, or Unknown. */
const cursorLabels = (d: SessionDetail): Record<Actor, string> =>
  ({ agent: d.session.agent ?? VERDICTS.agent.label, human: WORDS.aHuman, unsure: VERDICTS.unknown.label })

/** "0:52 of 1:36 · Agent": how the timeline reads where the replay is. */
function positionText(d: SessionDetail, ms: number) {
  const who = actorAt(d.timeline.segments, ms)
  return `${clock(ms)} of ${clock(d.timeline.duration_ms)}${who ? ` · ${cursorLabels(d)[who]}` : ""}`
}

function SessionBody({ d }: { d: SessionDetail }) {
  const s = d.session
  const replay = useReplay(d, (n, signal) => api.replayChunk(s.id, n, signal), cursorLabels(d))
  const live = replay.status !== "missing"
  const acted = s.share.human + s.share.agent + s.share.unsure > 0 // the actions Every action lists, by who took them
  return (
    <>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <VerdictBadge verdict={s.verdict} percent={d.percent} />{s.evidence && <ThinEvidenceTag />}{s.agent_turns && <TurnsBadge turns={s.agent_turns} />}
          {s.agent && <AgentTag name={s.agent} certainty={s.certainty} />}{s.verdict === "agent" && !s.agent && <UnnamedTag />}
        </div>
        <h1 className="text-3xl font-semibold">{d.title}</h1>
        <p className="text-sm text-muted-foreground">{s.when} · {duration(d.timeline.duration_ms)} · {d.pages.length} page{d.pages.length === 1 ? "" : "s"} · Session ID <span className="font-mono">{s.id}</span></p>
      </div>
      <Columns ratio="3-2">
        <div className="flex flex-col gap-5">
          <Card className="gap-0 py-0">
            <ReplayStage replay={replay} />
            {live && <ReplayControls replay={replay} durationMs={d.timeline.duration_ms} />}
          </Card>
          {replay.missing === "dropped" && <Alert variant="warn"><AlertDescription>{missingText("dropped")}</AlertDescription></Alert>}
          {replay.noPage && <Alert variant="info" data-replay-note="no-page"><AlertDescription>{WORDS.replayNoPage}</AlertDescription></Alert>}
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Timer className="size-5" aria-hidden />Activity timeline</CardTitle><CardAction><Legend /></CardAction></CardHeader>
            <CardContent className="flex flex-col gap-4">
              <SessionTimeline {...timelineView(d.timeline, { playheadMs: live ? replay.timeMs : undefined })}
                seek={live && replay.status === "ready" ? { durationMs: d.timeline.duration_ms, valueMs: replay.timeMs, valueText: positionText(d, replay.timeMs), onSeek: replay.seek } : undefined} />
              {acted ? <>
                <MiniTimeline human={s.share.human} agent={s.share.agent} unsure={s.share.unsure} segs={segsInTimeOrder(d.timeline.segments, s.share)} size="lg" />
                <p className="text-sm text-muted-foreground">{`${WORDS.shareOfActions} ${VERDICTS.human.label} ${s.share.human}%, ${VERDICTS.agent.label} ${s.share.agent}%, ${VERDICTS.unknown.label} ${s.share.unsure}%`}</p>
              </> : <p className="text-sm text-muted-foreground">{WORDS.noActions}</p>}
            </CardContent>
          </Card>
          <SessionPages pages={d.pages} onJump={replay.status === "ready" ? replay.jumpTo : undefined} />
        </div>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Search className="size-5" aria-hidden />Why this classification</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Alert variant="info"><Sparkles aria-hidden /><AlertDescription className="text-foreground"><span>{d.summary}</span></AlertDescription></Alert>
            {d.layers.map((layer) => <ReasonLayer key={layer.layer} layer={layer} />)}
          </CardContent>
        </Card>
      </Columns>
      <div>
        <SectionTitle aside={<span className="text-xs text-faint-foreground">{WORDS.serverHalfLead}</span>}>{WORDS.serverHalf}</SectionTitle>
        <ServerHalfTable server={d.server} />
      </div>
      <Actions d={d} replay={replay} />
    </>
  )
}

/** Every action, each time a link that moves the replay there. */
function Actions({ d, replay }: { d: SessionDetail; replay: ReplayState }) {
  const canSeek = replay.status === "ready"
  return (
    <div>
      <SectionTitle aside={<span className="text-xs text-faint-foreground">Text that visitors enter is masked.</span>}>All actions</SectionTitle>
      <Card className="py-0">
        <Table>
          <TableHeader><TableRow><TableHead>Time</TableHead><TableHead>Actor</TableHead><TableHead>Action</TableHead><TableHead className="max-md:hidden">Page</TableHead></TableRow></TableHeader>
          <TableBody>{d.actions.map((a, i) => (
            <TableRow key={`${a.at_ms}-${i}`}>
              <TableCell className="font-mono">{canSeek ? <Button variant="link" size="xs" onClick={() => replay.seek(a.at_ms)}>{clock(a.at_ms)}</Button> : clock(a.at_ms)}</TableCell>
              <TableCell><VerdictBadge verdict={a.who} /></TableCell><TableCell className="whitespace-normal">{a.what}</TableCell><TableCell className="font-mono max-md:hidden">{a.page}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      </Card>
    </div>
  )
}
