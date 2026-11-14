// What cake records and how it decides, and the session categories: two tables at the bottom of the dashboard, quieter
// than the Agent block (a plain framed Card + Table). The coverage wording comes from /api/overview (coverage), the
// categories from judging.en.json when the pages are built (src/lib/taxonomy.ts); never from the pages. DESIGN.md §16
import { Fragment, type ReactNode } from "react"
import { HelpCircle } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Coverage as CoverageText } from "@/data/types"
import { TAXONOMY, TURNS_ORDER, VERDICT_ORDER } from "@/lib/taxonomy"
import { TurnsBadge, VerdictBadge } from "./verdict"

export function Coverage({ coverage }: { coverage: CoverageText }) {
  const { columns, rows } = coverage
  return (
    <Card variant="flat" className="py-0" aria-label={coverage.title}>
      <Table>
        <TableHeader>
          <TableRow><TableHead>{columns.what}</TableHead><TableHead>{columns.shown_as}</TableHead><TableHead>{columns.how}</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.what}>
              <TableCell className="w-1/4 align-top whitespace-normal">{r.what}</TableCell>
              <TableCell className="w-1/4 align-top whitespace-normal">
                <span className="flex flex-wrap items-center gap-2"><VerdictBadge verdict={r.verdict} /><b>{r.shown_as}</b></span>
              </TableCell>
              <TableCell className="align-top whitespace-normal text-muted-foreground">{r.how}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}

/** The Bots number's "What's a bot?" help: the same wording as the coverage table (coverage.bot). */
export function BotHelp({ bot }: { bot: CoverageText["bot"] }) {
  return (
    <Tooltip>
      <TooltipTrigger aria-label={bot.question} className="inline-flex text-faint-foreground hover:text-foreground"><HelpCircle className="size-3.5" aria-hidden /></TooltipTrigger>
      <TooltipContent><b>{bot.question}</b> {bot.answer}</TooltipContent>
    </Tooltip>
  )
}

/** One category: its badge and its sentence, side by side and centred on each other. */
function CategoryRow({ mark, about }: { mark: ReactNode; about: string }) {
  return (
    <TableRow>
      <TableCell className="w-1/4 align-middle">{mark}</TableCell>
      <TableCell className="align-middle whitespace-normal text-muted-foreground">{about}</TableCell>
    </TableRow>
  )
}

/** The session categories: each verdict a session can get (Human, which counts what cake can't tell, marked;
 *  Agent; Bot), with Agent only and Human + agent, the two kinds of Agent session, right after Agent; every badge in
 *  one shape (only these, all aligned; no Unknown). */
export function Taxonomy() {
  const { verdicts, turns } = TAXONOMY
  return (
    <Card variant="flat" className="py-0" aria-label={TAXONOMY.title}>
      <Table>
        <TableBody>
          {VERDICT_ORDER.map((v) => (
            <Fragment key={v}>
              <CategoryRow mark={<VerdictBadge verdict={v} />} about={verdicts[v].about} />
              {v === "agent" && TURNS_ORDER.map((t) => <CategoryRow key={t} mark={<TurnsBadge turns={t} />} about={turns[t].about} />)}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}
