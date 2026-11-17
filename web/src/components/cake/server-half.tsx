// The session page's Server middleware (DESIGN.md §6.4): what the site's server saw of each page request, from the tokens that
// came with the session (SERVER.md), and the network cake.js's uploads came from (server mode only). Data from
// /api/session/<id> (`server`); with no rows it says why, in cake's words or the interface's.
import { Network as NetworkIcon } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Network, ServerHalf, ServerPage } from "@/data/types"
import { NO_VALUE, clock } from "@/lib/format"
import { WORDS } from "@/lib/words"

const fetchText = (f: ServerPage["fetch"]) => [f.site, f.mode, f.dest, f.user].map((v) => v ?? NO_VALUE).join(" · ")

function signatureText(s: ServerPage["signature"]) {
  if (!s) return "Not signed"
  return `${s.verified ? "Verified" : "Not verified"}${s.agent ? ` · ${s.agent}` : ""}`
}

const sameText = (same: boolean | null) => (same === null ? NO_VALUE : same ? "Same" : "Different")

/** "Country: US", "Published IP range: 203.0.113.0/24", "TLS JA4: t13d…", "Protocol: HTTP/2": each part only when known. */
function networkParts(n: Network) {
  return [["Country", n.country], ["Published IP range", n.range], ["TLS JA4", n.ja4], ["Protocol", n.protocol]]
    .filter(([, value]) => value).map(([name, value]) => `${name}: ${value}`)
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
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground"><NetworkIcon className="size-4 shrink-0" aria-hidden />{networkParts(server.network).map((part) => <span key={part}>{part}</span>)}</p>
      )}
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead><TableHead>Page</TableHead><TableHead className="max-md:hidden">Sec-Fetch: site/mode/dest/user</TableHead>
              <TableHead className="max-md:hidden">Signature</TableHead><TableHead>Same network as cake.js</TableHead>
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
