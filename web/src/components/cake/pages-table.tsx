// Top pages, one component for both lists (DESIGN.md §6): sorted by agent visits or by human visits, same columns and
// widths, numbers from the same list (top_pages of /api/overview). The first number column is the one it is sorted by.
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { PageVisits } from "@/data/types"
import { percent } from "@/lib/format"
import { SectionTitle } from "./bits"
import { MiniTimeline } from "./timeline"

const LABEL = { agent: "Agent visits", human: "Human visits" } as const

export function PagesTable({ title, by, pages }: { title: string; by: "agent" | "human"; pages: PageVisits[] }) {
  const other = by === "agent" ? "human" : "agent"
  const rows = [...pages].sort((a, b) => b[by] - a[by])
  return (
    <section aria-label={title}>
      <SectionTitle aside={<Button variant="link" size="sm" asChild><Link to="/sessions">All pages</Link></Button>}>{title}</SectionTitle>
      <Card className="py-0">
        <Table>
          <TableHeader><TableRow><TableHead>Page</TableHead><TableHead className="w-24 text-right">{LABEL[by]}</TableHead><TableHead className="w-24 text-right max-md:hidden">{LABEL[other]}</TableHead><TableHead className="w-1/4">Human and Agent</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((p) => {
              const h = percent(p.human, p.human + p.agent)
              return (
                <TableRow key={p.path}>
                  <TableCell className="font-mono whitespace-normal break-all">{p.path}</TableCell><TableCell className="text-right">{p[by]}</TableCell>
                  <TableCell className="text-right max-md:hidden">{p[other]}</TableCell><TableCell><MiniTimeline human={h} agent={100 - h} unsure={0} /></TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>
    </section>
  )
}
