// The "Server half" of a session (DESIGN.md §6): what the site's server saw of each page request, from the tokens that
// came with the session (SERVER.md), and the network cake.js's uploads came from (server mode only). Data from
// /api/session/<id> (`server`); with no rows it says why, in cake's words or the interface's.
import { Network as NetworkIcon } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Network, ServerHalf, ServerPage } from "@/data/types"
import { clock } from "@/lib/format"
import { WORDS } from "@/lib/words"

/** A value the request did not carry, or cake can't tell. */
const NONE = "—"

const fetchText = (f: ServerPage["fetch"]) => [f.site, f.mode, f.dest, f.user].map((v) => v ?? NONE).join(" · ")

function signatureText(s: ServerPage["signature"]) {
  if (!s) return "Not signed"
  return `${s.verified ? "Verified" : "Not verified"}${s.agent ? ` · ${s.agent}` : ""}`
}

const sameText = (same: boolean | null) => (same === null ? NONE : same ? "Same" : "Different")

function networkText(n: Network) {
  return [["country", n.country], ["published range", n.range], ["TLS JA4", n.ja4], ["", n.protocol]]
    .filter(([, value]) => value).map(([name, value]) => (name ? `${name} ${value}` : value)).join(" · ")
}

export function ServerHalfTable({ server }: { server: ServerHalf }) {
  if (!server.pages.length) {
    return (
      <Card variant="sunk" size="sm"><CardContent className="text-sm text-muted-foreground">{server.note ?? WORDS.serverHalfNone}</CardContent></Card>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {server.network && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground"><NetworkIcon className="size-4 shrink-0" aria-hidden />Network: {networkText(server.network)}</p>
      )}
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead><TableHead>Page</TableHead><TableHead className="max-md:hidden">Sec-Fetch site · mode · dest · user</TableHead>
              <TableHead className="max-md:hidden">Signature</TableHead><TableHead>cake.js network match</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>{server.pages.map((p, i) => (
            <TableRow key={`${p.at_ms}-${i}`}>
              <TableCell className="font-mono">{clock(p.at_ms)}</TableCell>
              <TableCell className="font-mono whitespace-normal">{p.path}</TableCell>
              <TableCell className="font-mono max-md:hidden">{fetchText(p.fetch)}</TableCell>
              <TableCell className="max-md:hidden">{signatureText(p.signature)}</TableCell>
              <TableCell>{sameText(p.same_network)}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      </Card>
      {server.note && <p className="text-sm text-muted-foreground">{server.note}</p>}
    </div>
  )
}
