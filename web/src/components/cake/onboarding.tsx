// "No data yet" layout used by every empty state: two columns, PostHog-style structure, Frosting look.
// Left: mascot, title, the ways to connect and their steps (OnboardingStep). Right: example preview.
// DESIGN.md §6 (empty states)
import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { Setup } from "@/data/types"
import { Crumb } from "./crumb"
import { SessionRow } from "./session-row"
import { SessionTimeline, timelineView } from "./timeline"
import { Legend } from "./verdict"

type Example = Setup["example"]

export function OnboardingLayout({ status, title, example, children }: {
  status: ReactNode; title: string; example: Example; children: ReactNode
}) {
  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,11fr)_minmax(0,9fr)]">
      <section className="flex flex-col gap-6">
        <Crumb pose="wave" className="w-36" />
        <div className="flex flex-col gap-2">
          <div>{status}</div>
          <h1 className="text-4xl font-semibold">{title}</h1>
        </div>
        {children}
      </section>
      <ExamplePreview example={example} />
    </div>
  )
}

/** One step of the onboarding: its number (none for a step that ends every way of connecting), its title and what to
 *  do. id names its heading. */
export function OnboardingStep({ n, id = `step-${n}`, title, children }: { n?: number; id?: string; title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2" aria-labelledby={id}>
      <h2 id={id} className="flex items-center gap-2 text-xl font-semibold">{n !== undefined && <Badge variant="tag">{n}</Badge>}{title}</h2>
      {children}
    </section>
  )
}

export function OrSeparator() {
  return (
    <div role="separator" className="flex items-center gap-3 text-sm font-extrabold text-faint-foreground">
      <span className="flex-1 border-t-2 border-dashed border-border" />Or<span className="flex-1 border-t-2 border-dashed border-border" />
    </div>
  )
}

/** What the lists will look like, from /api/setup's example (always labelled "example data"). */
export function ExamplePreview({ example, title = "Preview of your sessions" }: { example: Example; title?: string }) {
  return (
    <Card variant="sunk" className="lg:sticky lg:top-20" aria-label={`${title} (sample data)`}>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2"><h3 className="text-lg font-semibold">{title}</h3><Badge variant="tag">Sample data</Badge></div>
        <div className="pointer-events-none flex flex-col gap-2">
          {example.sessions.map((s) => <SessionRow key={s.id} s={s} compact />)}
        </div>
        <Card variant="flat" size="sm">
          <CardContent className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center justify-between gap-2"><b className="text-sm">Activity timeline</b><Legend /></div>
            <SessionTimeline {...timelineView(example.timeline, { compact: true })} />
          </CardContent>
        </Card>
      </CardContent>
    </Card>
  )
}
