// Top agents (DESIGN.md §6.1, §8): the range's Agent sessions by agent name, Unnamed together with its grey avatar,
// never a bot. The metric drawn is picked as on Trends (MetricPicker: Sessions first, then Visitors, Page views, Active
// time spent and Pages per session), each agent's number counted as the cards count it (/api/web's agents), the agents
// most first by it. One row per agent (AGENT_ROW_PX), so the axis names every agent however many there are (AgentTick:
// a long name ends with "…" and shows whole on hover); a horizontal bar each in the agent colour, its value at its end
// as the cards write it, in the tooltip too. An agent without a value for the metric (no visitor id, no time) keeps its
// row: no bar, and "—". The names' column and the room for the values are measured, not fixed: as wide as the longest
// name and the longest value need, and on a narrow screen no more than a share of the chart, so the bars keep room.
import { useEffect, useState } from "react"
import { Bot } from "lucide-react"
import { Bar, BarChart, LabelList, Rectangle, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import type { AgentNumbers } from "@/data/types"
import { NO_VALUE } from "@/lib/format"
import { useStyle } from "@/lib/style"
import { UNNAMED } from "@/lib/taxonomy"
import { WORDS } from "@/lib/words"
import { AGENT_ROW_PX, AgentTick, TICK_AVATAR } from "./avatar"
import { CardEmpty, InfoTip } from "./bits"
import { METRICS, MetricPicker, TooltipValue, type Metric } from "./metric-picker"

/** The thickest an agent's bar gets (px), so a few agents across a full-width card still read as bars, not blocks. */
const AGENT_BAR_PX = 32
/** Minimal style's bars (DESIGN.md §17): thinner, with smaller corners, as X's charts draw them. */
const MINIMAL_BAR_PX = 16
const MINIMAL_BAR_RADIUS = 2
/** The names' column (px): never narrower than an avatar and a short name, never wider than this on a wide card. */
const NAME_MIN_PX = 72
const NAME_MAX_PX = 200
/** The most of the chart's width the names' column takes, so a narrow screen keeps room for the bars. */
const NAME_SHARE = 0.4
/** Room between a bar's end and its value (px). */
const VALUE_GAP_PX = 8
/** Room on top of a measured name (px): recharts draws a y-axis tick left of the axis by its tick size and margin
 *  (6 + 2 px), and the canvas measures in fractions of a pixel, so a name measured to the pixel would be cut off. */
const NAME_SLACK_PX = 10
/** A character's rough width (px) where the page has no canvas to measure text with. */
const ROUGH_CHAR_PX = 7

let measurer: CanvasRenderingContext2D | null | undefined
/** How wide a text is in a font (px), from a canvas's text metrics. */
function textWidth(text: string, font: string): number {
  if (measurer === undefined) measurer = document.createElement("canvas").getContext("2d")
  if (!measurer || !font) return text.length * ROUGH_CHAR_PX
  measurer.font = font
  return measurer.measureText(text).width
}

/** An element's content width (px), kept up to date as it resizes; 0 until it is on the page. */
function useWidth(element: HTMLElement | null): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!element) return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [element])
  return width
}

/** The names' column and the room after the bars for the values (px), for these rows in a chart this wide and in the
 *  chart's font: a name on one line if it fits, the longest value whole. */
function chartRoom(rows: { name: string; shown: string }[], width: number, frame: HTMLElement | null) {
  const style = frame ? getComputedStyle(frame) : null
  const font = style ? `${style.fontWeight} ${style.fontSize} ${style.fontFamily}` : ""
  const bold = style ? `bold ${style.fontSize} ${style.fontFamily}` : ""
  const longestName = Math.max(0, ...rows.map((row) => textWidth(row.name, font)))
  const longestValue = Math.max(0, ...rows.map((row) => textWidth(row.shown, bold)))
  const most = width ? Math.min(NAME_MAX_PX, Math.max(NAME_MIN_PX, width * NAME_SHARE)) : NAME_MAX_PX
  return {
    names: Math.round(Math.min(most, Math.max(NAME_MIN_PX, TICK_AVATAR + Math.ceil(longestName) + NAME_SLACK_PX))),
    values: Math.ceil(longestValue) + VALUE_GAP_PX,
  }
}

export function TopAgentsChart({ agents }: { agents: AgentNumbers[] }) {
  const [metric, setMetric] = useState<Metric>("sessions")
  const { label, value, shown } = METRICS[metric]
  // most first by the metric; ties and agents without a value keep the API's order (most sessions first), those last.
  // An agent without a value gets a bar 0 long, labelled "—" (recharts labels no bar whose value is null).
  const rows = agents.map((agent) => ({ name: agent.name ?? UNNAMED, found: value(agent) }))
    .sort((a, b) => (b.found ?? -1) - (a.found ?? -1))
    .map(({ name, found }) => ({ name, value: found ?? 0, shown: found === null ? NO_VALUE : shown(found) }))
  const config = { value: { label, color: "var(--chart-2)" } } satisfies ChartConfig
  const [frame, setFrame] = useState<HTMLDivElement | null>(null)
  // drawn again when the style switch changes the font, so the names are measured in the new one
  const minimal = useStyle() === "minimal"
  const room = chartRoom(rows, useWidth(frame), frame)
  return (
    <Card>
      <CardHeader>
        <CardTitle icon={Bot}>{WORDS.agentsChart}<InfoTip label={`${WORDS.agentsChart} ${WORDS.chart}`} lines={[WORDS.agentsChartLead, WORDS.botsNotInChart]} /></CardTitle>
        <MetricPicker chart={WORDS.agentsChart} metric={metric} onMetric={setMetric} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-2">
        {rows.length ? (
          <ChartContainer ref={setFrame} config={config} height={rows.length * AGENT_ROW_PX} className="aspect-auto w-full">
            <BarChart data={rows} layout="vertical" margin={{ top: 0, bottom: 0, left: 0, right: room.values }} maxBarSize={minimal ? MINIMAL_BAR_PX : AGENT_BAR_PX}>
              <XAxis type="number" hide /><YAxis type="category" dataKey="name" width={room.names} interval={0} tickLine={false} axisLine={false} tick={<AgentTick />} />
              <ChartTooltip content={<ChartTooltipContent hideLabel={false} formatter={(_value, _name, item) => <TooltipValue label={label} shown={item.payload.shown} />} />} />
              {/* a shape of its own, drawn as the default one, makes recharts keep a bar 0 long, and its label "—" */}
              <Bar dataKey="value" fill="var(--color-value)" radius={minimal ? MINIMAL_BAR_RADIUS : 4} shape={<Rectangle />}><LabelList dataKey="shown" position="right" className="fill-foreground font-bold" /></Bar>
            </BarChart>
          </ChartContainer>
        ) : <CardEmpty text={WORDS.noAgentSessionsInRange} />}
      </CardContent>
    </Card>
  )
}
