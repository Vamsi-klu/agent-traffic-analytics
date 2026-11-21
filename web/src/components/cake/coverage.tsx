// The session categories at the bottom of the dashboard, quieter than the Agent block (a plain framed Card + Table),
// and the Script bot number's "What counts as a script bot" help. The categories' words come from judging.en.json when
// the pages are built (src/lib/taxonomy.ts), the bot help from /api/overview (coverage); never from the pages.
// DESIGN.md §16
import { CornerDownRight, HelpCircle } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table"
import type { Coverage as CoverageText } from "@/data/types"
import { TAXONOMY, TURNS_ORDER, VERDICT_ORDER } from "@/lib/taxonomy"
import { IconTip } from "./bits"
import { TurnsBadge, VerdictBadge } from "./verdict"

/** The Script bot number's "What counts as a script bot" help (coverage.bot of /api/overview): one paragraph, the
 *  question first. */
export function BotHelp({ bot }: { bot: CoverageText["bot"] }) {
  return <IconTip icon={HelpCircle} label={bot.question} text={<><b>{bot.question}</b> {bot.answer}</>} />
}

/** The session categories: the three verdicts (Human, which counts what cake can't tell, marked; Agent; Script bot),
 *  each a row with its badge and its sentence, centred on each other; Agent only and Human + agent, the two kinds of
 *  Agent session, are rows inside Agent, indented under it. Every badge in one shape; no Unknown. */
export function Taxonomy() {
  const { verdicts, turns } = TAXONOMY
  return (
    <Card variant="flat" className="py-0" aria-label={TAXONOMY.title}>
      <Table>
        <TableBody>
          {VERDICT_ORDER.flatMap((v) => [
            <TableRow key={v} data-category={v}>
              <TableCell className="w-1/4 align-middle"><VerdictBadge verdict={v} /></TableCell>
              <TableCell className="align-middle whitespace-normal text-muted-foreground">{verdicts[v].about}</TableCell>
            </TableRow>,
            ...(v === "agent" ? TURNS_ORDER.map((t) => (
              <TableRow key={t} data-category={t} data-inside="agent">
                <TableCell className="w-1/4 align-middle">
                  <span className="flex items-center gap-1.5 pl-3"><CornerDownRight className="size-4 shrink-0 text-faint-foreground" aria-hidden /><TurnsBadge turns={t} /></span>
                </TableCell>
                <TableCell className="align-middle whitespace-normal text-muted-foreground">{turns[t].about}</TableCell>
              </TableRow>
            )) : []),
          ])}
        </TableBody>
      </Table>
    </Card>
  )
}
