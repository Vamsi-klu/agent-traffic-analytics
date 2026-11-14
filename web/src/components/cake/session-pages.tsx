// The pages of one session, in the order they opened (DESIGN.md §6.4): the entry page and the exit page, then a
// row per page with when it opened, the page, how long the visit stayed, who acted there and its actions. With a replay
// to move, a row moves it to when its page opened and plays from there, as Jump to hand-off does; the row's time is the
// button keyboards reach. Data: `pages` of /api/session/<id>.
import { Route } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { SessionPage } from "@/data/types"
import { clock, duration } from "@/lib/format"
import { WORDS } from "@/lib/words"
import { WhoBadge } from "./verdict"

/** One of the two ends of the visit: a label and the page's path. */
function EndPage({ label, path }: { label: string; path: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
      <dt className="text-muted-foreground">{label}</dt><dd className="min-w-0 font-mono break-all">{path}</dd>
    </div>
  )
}

/** onJump: moves the replay to a moment and plays; leave it out when there is no replay to move. */
export function SessionPages({ pages, onJump }: { pages: SessionPage[]; onJump?: (ms: number) => void }) {
  const entry = pages[0], exit = pages[pages.length - 1]
  return (
    <Card className="pb-0" data-pages="">
      <CardHeader><CardTitle className="flex items-center gap-2"><Route className="size-5" aria-hidden />{WORDS.pagesVisited}</CardTitle></CardHeader>
      <CardContent>
        <dl className="flex flex-wrap gap-x-6 gap-y-1"><EndPage label={WORDS.entryPage} path={entry.path} /><EndPage label={WORDS.exitPage} path={exit.path} /></dl>
      </CardContent>
      <Table>
        <TableHeader>
          <TableRow><TableHead>Time</TableHead><TableHead>Page</TableHead><TableHead>Time on page</TableHead><TableHead>Main actor</TableHead><TableHead className="text-right max-md:hidden">Actions</TableHead></TableRow>
        </TableHeader>
        <TableBody>{pages.map((p, i) => (
          <TableRow key={`${p.at_ms}-${i}`} data-page-row="" className={onJump && "cursor-pointer"} onClick={onJump && (() => onJump(p.at_ms))}>
            <TableCell className="font-mono">{onJump ? <Button variant="link" size="xs">{clock(p.at_ms)}</Button> : clock(p.at_ms)}</TableCell>
            <TableCell className="font-mono whitespace-normal break-all">{p.path}</TableCell>
            <TableCell>{duration(p.duration_ms)}</TableCell>
            <TableCell>{p.who ? <WhoBadge who={p.who} /> : <span className="text-faint-foreground">—</span>}</TableCell>
            <TableCell className="text-right max-md:hidden">{p.actions}</TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
    </Card>
  )
}
