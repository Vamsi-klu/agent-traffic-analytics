// The dashboard's Trends (DESIGN.md §6.1, §8), as PostHog's web analytics draws its graph: the card's title, then the
// metric drawn, picked as on Top agents (MetricPicker: the five main metrics, Sessions first, with Clarity's words where
// Clarity defines one). One line for the Human and one for the Agent sessions (bots aren't in it), by the hour (Today),
// day (Last 7 and 30 days) or month (All time), as /api/web's trends gives them: sessions, visitors and page views are
// counts, active time spent and pages per session averages, so the lines are never stacked. An interval without such
// sessions has no average and is left empty, never drawn as 0; one between two empty ones shows as a dot. "Show as table"
// lists the numbers.
import { useState } from "react"
import { TrendingUp } from "lucide-react"
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { WebAnalytics } from "@/data/types"
import { NO_VALUE } from "@/lib/format"
import { WORDS } from "@/lib/words"
import { CardEmpty, InfoTip } from "./bits"
import { METRICS, MetricPicker, TooltipValue, type Metric } from "./metric-picker"
import { Legend, Swatch, VERDICTS } from "./verdict"

const config = {
  human: { label: VERDICTS.human.label, color: "var(--chart-1)" },
  agent: { label: VERDICTS.agent.label, color: "var(--chart-2)" },
} satisfies ChartConfig
type Who = keyof typeof config
const SWATCH: Record<Who, "h" | "a"> = { human: "h", agent: "a" }
/** The dot an interval gets in its verdict's colour when it has no line to draw (empty on both sides), in px. */
const DOT_RADIUS = 4
/** The least room between two labels on the time axis: over a long range recharts skips some to keep it, always labelling
 *  the first and the last, as PostHog's charts thin their labels out. */
const LABEL_GAP_PX = 24

export function TrendsChart({ trends }: { trends: WebAnalytics["trends"] }) {
  const [metric, setMetric] = useState<Metric>("sessions")
  const [table, setTable] = useState(false)
  const { value, shown, unit, whole } = METRICS[metric]
  const rows = trends.points.map((p) => ({ label: p.label, human: value(p.human), agent: value(p.agent) }))
  const sessions = trends.points.some((p) => p.human.sessions + p.agent.sessions > 0)
  const drawn = sessions && rows.some((row) => row.human !== null || row.agent !== null)
  const alone = (who: Who) => rows.map((row, i) => row[who] !== null && rows[i - 1]?.[who] == null && rows[i + 1]?.[who] == null)
  const dot = (who: Who) => {
    const single = alone(who)
    return function IntervalDot({ cx, cy, index = -1 }: { cx?: number; cy?: number; index?: number }) {
      return single[index] ? <circle key={`${who}-${index}`} cx={cx} cy={cy} r={DOT_RADIUS} fill={`var(--color-${who})`} /> : <g key={`${who}-${index}`} />
    }
  }
  const cell = (v: number | null) => (v === null ? NO_VALUE : shown(v))
  return (
    <Card>
      <CardHeader>
        <CardTitle icon={TrendingUp}>{WORDS.trends}<InfoTip label={`${WORDS.trends} ${WORDS.chart}`} lines={WORDS.about.trends} /></CardTitle>
        <CardAction><Legend unknown={false} /></CardAction>
        <MetricPicker chart={WORDS.trends} metric={metric} onMetric={setMetric} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-2">
        {drawn ? (
          <ChartContainer config={config} className="aspect-auto h-72 w-full">
            <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={LABEL_GAP_PX} />
              <YAxis width={46} tickLine={false} axisLine={false} unit={unit} allowDecimals={!whole} />
              <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => (
                <><Swatch kind={SWATCH[name as Who]} /><TooltipValue label={config[name as Who].label} shown={cell(typeof v === "number" ? v : null)} /></>
              )} />} />
              <Line dataKey="human" type="monotone" stroke="var(--color-human)" strokeWidth={2} dot={dot("human")} />
              <Line dataKey="agent" type="monotone" stroke="var(--color-agent)" strokeWidth={2} dot={dot("agent")} />
            </LineChart>
          </ChartContainer>
        ) : <CardEmpty text={sessions ? WORDS.noVisitorIds : WORDS.noSessionsInRange} />}
        <div className="mt-auto flex min-h-8 items-center">
          {drawn && <Button variant="link" size="sm" onClick={() => setTable(!table)}>{table ? WORDS.hideTable : WORDS.showAsTable}</Button>}
        </div>
        {table && drawn && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{WORDS.intervals[trends.interval]}</TableHead>
                <TableHead className="text-right">{VERDICTS.human.label}</TableHead>
                <TableHead className="text-right">{VERDICTS.agent.label}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.label}>
                  <TableCell>{row.label}</TableCell>
                  <TableCell className="text-right">{cell(row.human)}</TableCell>
                  <TableCell className="text-right">{cell(row.agent)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
