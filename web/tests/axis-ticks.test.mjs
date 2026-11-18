// The Trends chart's time axis (src/lib/axis-ticks.ts): which points it names, by the range's rule (/api/web's
// trends.every): the last 24 hours every 3 hours, the last 7 days every day, the last 30 days every 3 days, both ends
// named; All time each month's first day and the first point, by month. When labels would touch, the step doubles
// (months become quarters, then years), the spacing still even. Widths here are 6 px a character, the gap 8 px.
// Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { axisTicks, endText } from "../src/lib/axis-ticks.ts"

const when = JSON.parse(readFileSync(new URL("../../agentcake/data/api.en.json", import.meta.url), "utf8")).when
const WORDS = { months: when.months, monthYear: when.month_year }
const width = (text) => text.length * 6
const GAP = 8
const HOUR_MS = 3_600_000, DAY_MS = 24 * HOUR_MS
const pad = (n) => String(n).padStart(2, "0")

/** n hourly points from 2026-11-15 07:00, keyed and labelled as /api/web gives them. */
function hours(n) {
  return Array.from({ length: n }, (_, i) => {
    const t = new Date(Date.UTC(2026, 10, 15, 7) + i * HOUR_MS)
    const [day, hour] = [`${when.months[t.getUTCMonth()]} ${t.getUTCDate()}`, pad(t.getUTCHours())]
    return { key: `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())} ${hour}`, label: `${day}, ${hour}:00` }
  })
}

/** n daily points from the day `first` (a UTC date), labelled with the year when they cross a new year. */
function days(n, first) {
  const all = Array.from({ length: n }, (_, i) => new Date(first + i * DAY_MS))
  const years = new Set(all.map((t) => t.getUTCFullYear())).size > 1
  return all.map((t) => ({
    key: `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`,
    label: `${when.months[t.getUTCMonth()]} ${t.getUTCDate()}${years ? `, ${t.getUTCFullYear()}` : ""}`,
  }))
}

const at = (points, ticks) => ticks.map((tick) => points.findIndex((p) => p.label === tick.label))
const every = (step, last) => Array.from({ length: Math.floor(last / step) + 1 }, (_, i) => i * step)

test("Last 24 hours: every third hour, both ends, each named by its own label; every sixth when they would touch", () => {
  const points = hours(25)
  const wide = axisTicks(points, 3, 1022, width, GAP, WORDS)
  assert.deepEqual(at(points, wide), every(3, 24))
  assert.deepEqual(wide.map((t) => t.text), wide.map((t) => t.label))
  assert.deepEqual(at(points, axisTicks(points, 3, 355, width, GAP, WORDS)), every(6, 24))
})

test("Last 7 days: every day; every other day from the first when they would touch", () => {
  const points = days(8, Date.UTC(2026, 10, 9))
  assert.deepEqual(at(points, axisTicks(points, 1, 1022, width, GAP, WORDS)), every(1, 7))
  assert.deepEqual(at(points, axisTicks(points, 1, 200, width, GAP, WORDS)), every(2, 7))
})

test("Last 30 days: every third day, both ends; every sixth when they would touch", () => {
  const points = days(31, Date.UTC(2026, 9, 17))
  assert.deepEqual(at(points, axisTicks(points, 3, 1022, width, GAP, WORDS)), every(3, 30))
  assert.deepEqual(at(points, axisTicks(points, 3, 355, width, GAP, WORDS)), every(6, 30))
})

test("All time: each month's first day and the first point, named by month; the same days by the 30-day rule every third", () => {
  const points = days(32, Date.UTC(2026, 9, 16))
  const months = axisTicks(points, "month", 1022, width, GAP, WORDS)
  assert.deepEqual(months.map((t) => t.text), ["Oct 2026", "Nov 2026"])
  assert.deepEqual(at(points, months), [0, 16], "Oct 16, the first, and Nov 1")
  assert.deepEqual(at(points, axisTicks(points, 3, 1022, width, GAP, WORDS)), every(3, 30))
  const short = days(18, Date.UTC(2026, 10, 3))
  assert.deepEqual(axisTicks(short, "month", 1022, width, GAP, WORDS).map((t) => t.text), ["Nov 2026"], "within one month: its name")
})

test("All time over 400 days: months, then quarters when months would touch; the first point gives way when it would", () => {
  const points = days(400, Date.UTC(2025, 9, 14))
  const wide = axisTicks(points, "month", 1022, width, GAP, WORDS)
  assert.deepEqual(wide.map((t) => t.text), ["Nov 2025", "Dec 2025", "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026",
    "Jun 2026", "Jul 2026", "Aug 2026", "Sep 2026", "Oct 2026", "Nov 2026"], "Oct 14 is too close to Nov 1 to be named too")
  const narrow = axisTicks(points, "month", 355, width, GAP, WORDS)
  assert.deepEqual(narrow.map((t) => t.text), ["Oct 2025", "Jan 2026", "Apr 2026", "Jul 2026", "Oct 2026"])
  const years = axisTicks(days(1000, Date.UTC(2024, 0, 1)), "month", 355, width, GAP, WORDS)
  assert.deepEqual(years.map((t) => t.text), ["Jan 2024", "Jan 2025", "Jan 2026"], "then years")
})

test("the labels never touch: each pair at least the gap apart, at every width", () => {
  for (const [points, rule] of [[hours(25), 3], [days(8, Date.UTC(2026, 10, 9)), 1], [days(31, Date.UTC(2026, 9, 17)), 3],
    [days(400, Date.UTC(2025, 9, 14)), "month"]]) {
    for (const plot of [1022, 355, 240]) {
      const ticks = axisTicks(points, rule, plot, width, GAP, WORDS), px = plot / (points.length - 1), where = at(points, ticks)
      for (let i = 1; i < ticks.length; i += 1) {
        const room = (width(ticks[i - 1].text) + width(ticks[i].text)) / 2 + GAP
        assert.ok((where[i] - where[i - 1]) * px >= room, `${rule} at ${plot}: ${ticks[i - 1].text} and ${ticks[i].text}`)
      }
    }
  }
})

test("the last label the rule writes, whose half the chart leaves room for at its right end", () => {
  assert.equal(endText(hours(25), 3, WORDS), "Nov 16, 07:00")
  assert.equal(endText(days(8, Date.UTC(2026, 10, 9)), 1, WORDS), "Nov 16")
  assert.equal(endText(days(30, Date.UTC(2026, 9, 17)), 3, WORDS), "Nov 13", "the 28th of 30 days: the last one named")
  assert.equal(endText(days(32, Date.UTC(2026, 9, 16)), "month", WORDS), "Nov 2026", "the last first of a month")
  assert.equal(endText(days(10, Date.UTC(2026, 10, 3)), "month", WORDS), "Nov 2026", "none: the first point's month")
})
