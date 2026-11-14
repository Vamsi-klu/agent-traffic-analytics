// What a page shows before its data is there (DESIGN.md §6.3): PageLoading while /api answers, PageError when it
// can't, and Loaded to pick between them and the page. Made of Crumb, Card and Button only.
import type { ReactNode } from "react"
import { RotateCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { ApiState } from "@/data/api"
import { Crumb } from "./crumb"

/** Quiet on purpose: it fades in only when loading takes a moment, so a quick answer never flashes it (shown at once
 *  with reduced motion, where the fade is off). */
export function PageLoading({ what }: { what: string }) {
  return (
    <div role="status" className="flex animate-in items-center justify-center gap-3 py-10 text-sm text-muted-foreground fade-in fill-mode-both delay-300">
      <Crumb pose="look" className="w-16" title="Crumb is looking." />Loading {what}…
    </div>
  )
}

/** What happened and what to do: the message comes from the API (or says cake can't be reached). */
export function PageError({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return (
    <Card variant="sunk" role="alert">
      <CardContent className="flex flex-col items-center gap-3 py-6 text-center">
        <Crumb pose="oops" className="w-32" title="Crumb: something went wrong." />
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{message}</p>
        {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RotateCw aria-hidden />Try again</Button>}
      </CardContent>
    </Card>
  )
}

/** The page once its data is ready; until then PageLoading, or PageError with "Try again" (none for a missing
 *  session: trying again won't bring it back). `what` names the data: "the dashboard", "this session". */
export function Loaded<T>({ state, what, children }: { state: ApiState<T>; what: string; children: (data: T) => ReactNode }) {
  if (state.status === "ready") return <>{children(state.data)}</>
  if (state.status === "loading") return <PageLoading what={what} />
  const missing = state.error.status === 404
  return <PageError title={`Couldn't load ${what}`} message={state.error.message} onRetry={missing ? undefined : state.retry} />
}
