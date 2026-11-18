// The dashboard's Trends (DESIGN.md §6.1, §8), as PostHog's web analytics draws its graph: the card's title, then the
// metric drawn, picked as on Top agents (MetricPicker: the five main metrics, Sessions first, with Clarity's words where
// Clarity defines one). One line for the Human and one for the Agent sessions (bots aren't in it), by the hour (Last 24
// hours) or by the day (Last 7 and 30 days, All time), as /api/web's trends gives them: sessions, visitors and page views are
// counts, active time spent and pages per session averages, so the lines are never stacked. An interval without such
// sessions has no average and is left empty, never drawn as 0; one between two empty ones shows as a dot. The time axis
// names the points the range's rule picks (src/lib/axis-ticks.ts: every 3 hours, every day, every 3 days, or each
// month), measured against the plot's width so the labels never touch. "Show as table" lists the numbers.
import { useEffect, useMemo, useRef, useState } from "react"
import { TrendingUp } from "lucide-react"
import { CartesianGrid, Line, LineChart, XAxis, YAxis, usePlotArea } from "recharts"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { WebAnalytics } from "@/data/types"
import { axisTicks, endText, type MonthWords } from "@/lib/axis-ticks"
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
/** The least room between two labels on the time axis, in px: where they'd have less, the step between them doubles. */
const LABEL_GAP_PX = 8
/** The room at the chart's right end, in px, beyond what the last label needs. */
const END_PX = 8
/** The month names the time axis writes months with, from the API's own words (api.en.json, vite.config.ts). */
const MONTHS: MonthWords = import.meta.env.VITE_MONTHS

/** Tells the chart how wide its plot is (recharts' plot area, the y-axis left out), again whenever it changes. */
function PlotWidth({ onWidth }: { onWidth: (width: number) => void }) {
  const width = usePlotArea()?.width
  useEffect(() => { if (width) onWidth(width) }, [width, onWidth])
  return null
}

/** timeZone: what the note under the chart calls the time zone of its days and hours (/api/web's time_zone). */
export function TrendsChart({ trends, timeZone }: { trends: WebAnalytics["trends"]; timeZone: string }) {
  const [metric, setMetric] = useState<Metric>("sessions")
  const [table, setTable] = useState(false)
  const { value, shown, unit, whole } = METRICS[metric]
  const rows = trends.points.map((p) => ({ label: p.label, human: value(p.human), agent: value(p.agent) }))
  const chart = useRef<HTMLDivElement>(null)
  const [plotWidth, setPlotWidth] = useState(0)
  const [measure, setMeasure] = useState<((text: string) => number) | null>(null)
  // the labels' widths in the axis's own font (a canvas measures text as the SVG draws it), again once the fonts are in
  useEffect(() => {
    const pen = document.createElement("canvas").getContext("2d")
    if (!chart.current || !pen) return
    const look = getComputedStyle(chart.current)
    const ready = () => {
      pen.font = `${look.fontStyle} ${look.fontWeight} ${look.fontSize} ${look.fontFamily}`
      setMeasure(() => (text: string) => pen.measureText(text).width)
    }
    ready()
    void document.fonts?.ready.then(ready)
  }, [])
  const ticks = useMemo(() => (measure && plotWidth ? axisTicks(trends.points, trends.every, plotWidth, measure, LABEL_GAP_PX, MONTHS) : []),
    [trends, plotWidth, measure])
  const tickText = new Map(ticks.map((tick) => [tick.label, tick.text]))
  const last = measure && endText(trends.points, trends.every, MONTHS)
  const end = Math.max(END_PX, last ? Math.ceil(measure(last) / 2) : 0)
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
          <ChartContainer ref={chart} config={config} className="aspect-auto h-72 w-full">
            <LineChart data={rows} margin={{ left: 0, right: end, top: 8 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} ticks={ticks.map((tick) => tick.label)} interval={0}
                tickFormatter={(label: string) => tickText.get(label) ?? label} />
              <PlotWidth onWidth={setPlotWidth} />
              <YAxis width={46} tickLine={false} axisLine={false} unit={unit} allowDecimals={!whole} />
              <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => (
                <><Swatch kind={SWATCH[name as Who]} /><TooltipValue label={config[name as Who].label} shown={cell(typeof v === "number" ? v : null)} /></>
              )} />} />
              <Line dataKey="human" type="monotone" stroke="var(--color-human)" strokeWidth={2} dot={dot("human")} />
              <Line dataKey="agent" type="monotone" stroke="var(--color-agent)" strokeWidth={2} dot={dot("agent")} />
            </LineChart>
          </ChartContainer>
        ) : <CardEmpty text={sessions ? WORDS.noVisitorIds : WORDS.noSessionsInRange} />}
        <div className="mt-auto flex min-h-8 items-center justify-between gap-3">
          {drawn && <Button variant="link" size="sm" onClick={() => setTable(!table)}>{table ? WORDS.hideTable : WORDS.showAsTable}</Button>}
          {drawn && <span className="text-xs text-muted-foreground">{WORDS.timesIn(timeZone)}</span>}
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
