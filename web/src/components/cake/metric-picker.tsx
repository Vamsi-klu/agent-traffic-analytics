// The metric the dashboard's charts draw, picked the same way on each (DESIGN.md §6.1, §8), as PostHog's web analytics
// picks its graph's: a Select naming the metric, under the card's title and as tall as every other dropdown (Sessions
// first, then Visitors, Page views, Active time spent and Pages per session: the five main metrics, named as their total
// cards are, whose information icons say what each means, so the picker needs none). Trends and Top agents use it. A
// value reads the same on the charts, in their hovers (TooltipValue) and on the total cards: counts whole, active time in
// minutes, pages per session with one decimal.
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { TrendNumbers } from "@/data/types"
import { minutes } from "@/lib/format"
import { WORDS, metricName } from "@/lib/words"

export type Metric = "sessions" | "visitors" | "page_views" | "active_time" | "pages_per_session"
/** Active time spent in minutes, rounded as it is written (one decimal), from milliseconds. */
export const activeMinutes = (ms: number) => Number(minutes(ms))
/** Each metric: its name, its value for a group of sessions (null: none), how a value reads, the y-axis unit and
 *  whether it counts (whole numbers). */
export const METRICS: Record<Metric, { label: string; value: (n: TrendNumbers) => number | null; shown: (v: number) => string; unit?: string; whole?: boolean }> = {
  sessions: { label: metricName(WORDS.sessions), value: (n) => n.sessions, shown: String, whole: true },
  visitors: { label: metricName(WORDS.visitors), value: (n) => n.visitors, shown: String, whole: true },
  page_views: { label: metricName(WORDS.pageViews), value: (n) => n.page_views, shown: String, whole: true },
  active_time: { label: metricName(WORDS.activeTime), value: (n) => (n.active_ms === null ? null : activeMinutes(n.active_ms)), shown: (v) => `${v.toFixed(1)} min`,
    unit: " min" },
  pages_per_session: { label: metricName(WORDS.pagesPerSession), value: (n) => n.pages_per_session, shown: (v) => v.toFixed(1) },
}
const ORDER = Object.keys(METRICS) as Metric[]

/** A chart's hover line: a name (the metric's, or a series') and its value as METRICS writes it, in the tooltip's own text
 *  colour. */
export function TooltipValue({ label, shown }: { label: string; shown: string }) {
  return (
    <div className="flex flex-1 items-center justify-between gap-2 leading-none">
      <span>{label}</span><span className="font-mono font-medium tabular-nums">{shown}</span>
    </div>
  )
}

/** chart: the chart's title, which names its Select for screen readers ("Trends: Metric"). */
export function MetricPicker({ chart, metric, onMetric }: { chart: string; metric: Metric; onMetric: (metric: Metric) => void }) {
  return (
    <Select value={metric} onValueChange={(v) => { onMetric(v as Metric) }}>
      <SelectTrigger aria-label={`${chart}: ${WORDS.metric}`}><SelectValue /></SelectTrigger>
      <SelectContent>{ORDER.map((m) => <SelectItem key={m} value={m}>{METRICS[m].label}</SelectItem>)}</SelectContent>
    </Select>
  )
}
