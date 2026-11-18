// Which points the Trends chart's time axis names (DESIGN.md §8), by the range's rule (/api/web's trends.every, as
// PostHog's charts name them): every Nth point from the first (the last 24 hours every 3 hours, the last 7 days every
// day, the last 30 days every 3 days: both ends named), or each month's first day and the first point, by month (All
// time: "Nov 2026"). Where the labels would touch (a narrow screen), the step doubles (6 hours, 2 days, 6 days;
// months become quarters, then years) until they don't, the spacing even again; the first point gives way to a month
// too close after it. The points, the hover and the table keep each point's own label. endText() is the last label the
// rule writes, which the chart leaves room for at its right end (a label is centred on its point).

/** A point as /api/web gives it: its hour or day ("2026-11-15 07", "2026-11-15") and its label. */
export type AxisPoint = { key: string; label: string }
/** A label the axis writes: under the point whose label is `label`, the text `text`. */
export type AxisTick = { label: string; text: string }
/** The month names and the "{month} {year}" a month is written with (api.en.json "when"). */
export type MonthWords = { months: string[]; monthYear: string }

/** Months, quarters and years, each counted from January: the steps All time's labels take. */
const MONTH_STEPS = [1, 3, 12]

/** "Nov 2026": the month of a point's key, as the axis writes months. */
function monthText(key: string, words: MonthWords) {
  const [year, number] = key.split("-")
  return words.monthYear.replace("{month}", words.months[Number(number) - 1]).replace("{year}", year)
}

/** The text of the last point the rule names at its own step: the chart leaves half its width at the right end, where
 *  a label centred on a point near the end would be cut off. Doubling the step only ever drops labels, so this one is
 *  the furthest right there can be, and the room depends on the data alone, not on the width. */
export function endText(points: AxisPoint[], every: number | "month", words: MonthWords): string | null {
  if (!points.length) return null
  if (every === "month") {
    const starts = points.filter((p) => p.key.split("-")[2].startsWith("01"))
    return monthText((starts.at(-1) ?? points[0]).key, words)
  }
  return points[Math.floor((points.length - 1) / every) * every].label
}

/** The ticks for points on a plot `plotWidth` px wide, every: N or "month"; width(text) is how wide a label is in px, gap
 *  the least room between two labels. */
export function axisTicks(points: AxisPoint[], every: number | "month", plotWidth: number, width: (text: string) => number,
  gap: number, words: MonthWords): AxisTick[] {
  if (!points.length) return []
  const px = plotWidth / Math.max(points.length - 1, 1)
  const ticks = (at: number[], text: (i: number) => string) => at.map((i) => ({ at: i, text: text(i) }))
  const apart = (a: { at: number; text: string }, b: { at: number; text: string }) =>
    (b.at - a.at) * px >= (width(a.text) + width(b.text)) / 2 + gap
  const fits = (picked: { at: number; text: string }[]) => picked.every((tick, i) => i === 0 || apart(picked[i - 1], tick))
  const named = (picked: { at: number; text: string }[]) => picked.map((tick) => ({ label: points[tick.at].label, text: tick.text }))
  if (every === "month") {
    const month = (i: number) => monthText(points[i].key, words)
    let picked: { at: number; text: string }[] = []
    for (const months of MONTH_STEPS) {
      const starts = points.flatMap((p, i) => {
        const [, number, day] = p.key.split("-")
        return day.startsWith("01") && (Number(number) - 1) % months === 0 ? [i] : []
      })
      picked = ticks(starts[0] === 0 ? starts : [0, ...starts], month)
      if (picked.length > 1 && starts[0] !== 0 && !apart(picked[0], picked[1])) picked = picked.slice(1)
      if (fits(picked)) break
    }
    return named(picked)
  }
  for (let step = every; ; step *= 2) {
    const picked = ticks(points.flatMap((_, i) => (i % step === 0 ? [i] : [])), (i) => points[i].label)
    if (fits(picked) || picked.length <= 1) return named(picked)
  }
}
