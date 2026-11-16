// The dashboard's Trends and four tables under Deep dive in Chromium, against the built app and the sample /api/overview,
// /api/web and /api/setup. Trends: the metric picked in its Select (Sessions first, the five main metrics), one line for
// Human and one for Agent, an interval without sessions counted as 0 but without an average, Clarity's words only where
// Clarity defines the metric, by the hour for Today. The four tables, one component (Paths, Sources, Devices,
// Geography): the title in the card, a breakdown's Select and All / Agent / Human; each row's sessions (bold), visitors
// and page views of the sessions picked, most first, and with All the Agent sessions' share (bold); a row's hover splits
// each number into Agent and Human; ten rows, then Show all; a value opens its sessions; only the table scrolls at 485.
// Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { minutes } from "../src/lib/format.ts"
import { WORDS } from "../src/lib/words.ts"
import { openTab, sample, scrolled, startApp } from "./app.mjs"

const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const web = sample("web"), setup = sample("setup")
const RECORDED = { ...setup, recorded: { sessions: 9, site: 9, agent: 4 } }
/** An interval without sessions, as /api/web gives it. */
const NONE = { sessions: 0, visitors: 0, page_views: 0, active_ms: null, pages_per_session: null }
const TABLES = [WORDS.paths, WORDS.web.titles.sources, WORDS.web.titles.devices, WORDS.web.titles.geography]

async function open({ webAnswer, width } = {}) {
  const tab = await openTab(app, { width })
  if (webAnswer) await tab.page.route("**/api/web**", (route) => route.fulfill({ json: webAnswer }))
  await tab.page.route("**/api/setup", (route) => route.fulfill({ json: RECORDED }))
  await tab.page.goto(app.url("#/dashboard"))
  await tab.page.getByRole("region", { name: WORDS.totals }).waitFor({ timeout: WAIT_MS })
  return tab
}

const trendsCard = (page) => page.locator('[data-slot="card"]').filter({ has: page.locator('[data-slot="card-title"]', { hasText: new RegExp(`^${WORDS.trends}$`) }) })
const cellTexts = (rows) => rows.evaluateAll((trs) => trs.map((tr) => [...tr.cells].map((cell) => cell.textContent.trim())))
const table = (page, title) => page.getByRole("region", { name: title, exact: true })
async function pick(page, combobox, option) {
  await combobox.click()
  await page.getByRole("option", { name: option, exact: true }).click()
}
const share = (row) => `${Math.round((100 * row.agent) / (row.agent + row.human))}%`
/** The rows of a kind, most of its sessions first (ties as the API sent them), as the table orders them. */
const ofKind = (rows, sessions) => rows.filter((row) => sessions(row) > 0).sort((a, b) => sessions(b) - sessions(a))

test("Trends opens on Sessions; its Select lists the five main metrics, named as their total cards are; a line each for Human and Agent", async () => {
  const tab = await open()
  try {
    const card = trendsCard(tab.page)
    const metric = card.getByRole("combobox", { name: WORDS.metric })
    assert.equal((await metric.innerText()).trim(), "Sessions")
    await metric.click()
    assert.deepEqual(await tab.page.getByRole("option").allInnerTexts(), ["Sessions", "Visitors", "Page views", "Active time spent", "Pages per session"])
    await tab.page.keyboard.press("Escape")
    assert.equal(await card.locator(".recharts-line-curve").count(), 2, "one line for Human, one for Agent")
    assert.match(await card.innerText(), /Human[\s\S]*Agent/, "a legend")
  } finally { await tab.close() }
})

test("Trends has no information icon beside its metric, which its total card explains; its title's icon says what the chart shows", async () => {
  const tab = await open()
  try {
    const card = trendsCard(tab.page)
    const metric = card.getByRole("combobox", { name: WORDS.metric })
    for (const name of ["Sessions", "Visitors", "Page views", "Active time spent", "Pages per session"]) {
      if (name !== "Sessions") await pick(tab.page, metric, name)
      assert.equal(await card.getByRole("button", { name: `About ${name}`, exact: true }).count(), 0, name)
    }
    const help = card.getByRole("button", { name: `About ${WORDS.trends} ${WORDS.chart}`, exact: true })
    await help.scrollIntoViewIfNeeded() // a scroll closes a tooltip, so the page is still before the focus
    await scrolled(tab.page)
    await help.focus() // a tooltip opens on focus, as for a keyboard user
    await tab.page.getByRole("tooltip").filter({ hasText: WORDS.about.trends[0] }).waitFor({ timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("Trends counts an interval without sessions as 0 but gives it no average; its table says so", async () => {
  const points = web.trends.points.map((p, i) => (i === 1 ? { label: p.label, agent: NONE, human: NONE } : p))
  const [first] = points
  assert.ok(first.human.active_ms && first.agent.active_ms, "the sample's first day has both")
  const tab = await open({ webAnswer: { ...web, trends: { ...web.trends, points } } })
  try {
    const card = trendsCard(tab.page)
    await card.getByRole("button", { name: WORDS.showAsTable }).click()
    const grid = card.locator("table")
    assert.deepEqual((await grid.locator("thead th").allInnerTexts()).map((t) => t.trim()), [WORDS.intervals.day, "Human", "Agent"])
    let rows = await cellTexts(grid.locator("tbody tr"))
    assert.deepEqual(rows[1], [points[1].label, "0", "0"])
    assert.deepEqual(rows[0], [first.label, String(first.human.sessions), String(first.agent.sessions)])
    await pick(tab.page, card.getByRole("combobox", { name: WORDS.metric }), "Active time spent")
    rows = await cellTexts(grid.locator("tbody tr"))
    assert.deepEqual(rows[1], [points[1].label, "—", "—"], "no average, not 0 min")
    assert.deepEqual(rows[0], [first.label, `${minutes(first.human.active_ms)} min`, `${minutes(first.agent.active_ms)} min`])
    await pick(tab.page, card.getByRole("combobox", { name: WORDS.metric }), "Pages per session")
    rows = await cellTexts(grid.locator("tbody tr"))
    assert.deepEqual(rows[0], [first.label, first.human.pages_per_session.toFixed(1), first.agent.pages_per_session.toFixed(1)])
  } finally { await tab.close() }
})

test("Today's Trends come by the hour", async () => {
  const hours = ["00:00", "01:00", "02:00"].map((label, i) => ({ label, agent: { ...NONE, sessions: i }, human: { ...NONE, sessions: i + 1 } }))
  const tab = await open({ webAnswer: { ...web, trends: { interval: "hour", points: hours } } })
  try {
    const card = trendsCard(tab.page)
    await card.getByRole("button", { name: WORDS.showAsTable }).click()
    assert.equal((await card.locator("thead th").first().innerText()).trim(), WORDS.intervals.hour)
    assert.deepEqual((await cellTexts(card.locator("tbody tr"))).map((row) => row[0]), ["00:00", "01:00", "02:00"])
  } finally { await tab.close() }
})

test("the four tables are one component: the title in the card, a breakdown's Select, All / Agent / Human; no All pages link", async () => {
  const tab = await open()
  try {
    const opensWith = { [WORDS.paths]: null, [WORDS.web.titles.sources]: "Channel", [WORDS.web.titles.devices]: "Device type", [WORDS.web.titles.geography]: "Region" }
    for (const title of TABLES) {
      const region = table(tab.page, title)
      assert.equal((await region.locator('[data-slot="card-title"]').innerText()).trim(), title, `${title}: the card's own title`)
      assert.deepEqual(await region.getByRole("radio").allInnerTexts(), ["All", "Agent", "Human"], title)
      assert.equal(await region.getByRole("radio", { name: "All" }).getAttribute("aria-checked"), "true", `${title} opens on All`)
      const breakdown = region.getByRole("combobox")
      assert.equal(await breakdown.count(), opensWith[title] ? 1 : 0, title)
      if (opensWith[title]) assert.equal((await breakdown.innerText()).trim(), opensWith[title])
      assert.ok((await region.innerText()).includes(WORDS.web.botsNote), `${title}: bots aren't counted`)
    }
    assert.equal(await tab.page.getByRole("link", { name: "All pages" }).count(), 0)
  } finally { await tab.close() }
})

test("a table shows each row's sessions (bold), visitors and page views of all its sessions, and the Agent sessions' share (bold), most sessions first", async () => {
  for (const width of [1280, 485]) {
    const tab = await open({ width })
    try {
      const region = table(tab.page, WORDS.paths)
      assert.deepEqual((await region.locator("thead th").allInnerTexts()).map((t) => t.trim()), [WORDS.path, "Sessions", "Visitors", "Page views", WORDS.web.agentShare])
      const expected = ofKind(web.paths, (p) => p.agent + p.human).map((p) => [p.path, String(p.agent + p.human), String(p.visitors ?? "—"), String(p.page_views), share(p)])
      assert.deepEqual(await cellTexts(region.locator("tbody tr")), expected, `at ${width}`)
      const weights = await region.locator("tbody tr").first().locator("td").evaluateAll((tds) => tds.map((td) => Number(getComputedStyle(td).fontWeight)))
      assert.ok(weights[1] >= 700 && weights[4] >= 700, `sessions and the share are bold: ${weights}`)
      assert.ok(weights[2] < 700 && weights[3] < 700, `visitors and page views are not: ${weights}`)
      const [scroll, client] = await tab.page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
      assert.ok(scroll <= client, `the page doesn't scroll sideways at ${width}`)
      if (width === 485) {
        const [inside, box] = await region.locator('[data-slot="table-container"]').evaluate((el) => [el.scrollWidth, el.clientWidth])
        assert.ok(inside > box, "the table scrolls inside its card")
      }
    } finally { await tab.close() }
  }
})

test("Agent or Human counts only those sessions, ordered by them, without the share", async () => {
  const tab = await open()
  try {
    const region = table(tab.page, WORDS.web.titles.sources)
    const rows = web.tables.sources.find((d) => d.dimension === "channel").rows
    for (const [kind, sessions, visitors, views] of [["Agent", "agent", "agent_visitors", "agent_page_views"], ["Human", "human", "human_visitors", "human_page_views"]]) {
      await region.getByRole("radio", { name: kind }).click()
      assert.deepEqual((await region.locator("thead th").allInnerTexts()).map((t) => t.trim()), ["Channel", "Sessions", "Visitors", "Page views"], kind)
      const expected = ofKind(rows, (r) => r[sessions]).map((r) => [r.value, String(r[sessions]), String(r[visitors] ?? "—"), String(r[views])])
      assert.deepEqual(await cellTexts(region.locator("tbody tr")), expected, kind)
    }
  } finally { await tab.close() }
})

test("hovering a row splits each of its numbers into Agent and Human", async () => {
  const tab = await open()
  try {
    const top = ofKind(web.paths, (p) => p.agent + p.human)[0]
    await table(tab.page, WORDS.paths).locator("tbody tr").first().hover()
    const tip = tab.page.getByRole("tooltip").filter({ hasText: "Page views:" })
    await tip.waitFor({ timeout: WAIT_MS })
    const text = (await tip.innerText()).replace(/\s+/g, " ")
    for (const line of [`Sessions: ${top.agent} Agent, ${top.human} Human`, `Visitors: ${top.agent_visitors} Agent, ${top.human_visitors} Human`,
      `Page views: ${top.agent_page_views} Agent, ${top.human_page_views} Human`]) assert.ok(text.includes(line), `${line} in ${text}`)
  } finally { await tab.close() }
})

test("ten rows, then Show all N opens the rest in place, and Show fewer closes them", async () => {
  const paths = Array.from({ length: 12 }, (_, i) => ({ path: `/p${i}`, agent: 12 - i, human: i, visitors: 12, agent_visitors: 6, human_visitors: 6,
    page_views: 20, agent_page_views: 10, human_page_views: 10 }))
  const tab = await open({ webAnswer: { ...web, paths, shown: 10 } })
  try {
    const region = table(tab.page, WORDS.paths)
    assert.equal(await region.locator("tbody tr").count(), 10)
    await region.getByRole("button", { name: WORDS.web.showAll(12) }).click()
    assert.equal(await region.locator("tbody tr").count(), 12)
    await region.getByRole("button", { name: WORDS.web.showFewer }).click()
    assert.equal(await region.locator("tbody tr").count(), 10)
  } finally { await tab.close() }
})

test("a value opens Session replay narrowed to its sessions; a region reads Country – name; without a load balancer the place says it comes only on a server", async () => {
  const tab = await open()
  try {
    const sources = table(tab.page, WORDS.web.titles.sources)
    const top = ofKind(web.tables.sources.find((d) => d.dimension === "channel").rows, (r) => r.agent + r.human)[0]
    const href = await sources.getByRole("link", { name: WORDS.web.watch(top.value) }).getAttribute("href")
    const query = new URLSearchParams(href.split("?")[1])
    assert.deepEqual([query.get("dimension"), query.get("key"), query.get("label")], ["channel", top.key, top.value])
    const region = ofKind(web.tables.geography.find((d) => d.dimension === "region").rows, (r) => r.agent + r.human)[0]
    const geography = table(tab.page, WORDS.web.titles.geography)
    assert.equal((await geography.locator("tbody tr").first().locator("td").first().innerText()).trim(),
      `${new Intl.DisplayNames(["en"], { type: "region" }).of(region.country)} – ${region.value}`)
  } finally { await tab.close() }
  const noPlace = { ...web, place: false, tables: { ...web.tables, geography: web.tables.geography.map((d) => (["country", "region", "city"].includes(d.dimension) ? { ...d, rows: [] } : d)) } }
  const local = await open({ webAnswer: noPlace })
  try {
    assert.match(await table(local.page, WORDS.web.titles.geography).innerText(), /Country, region, and city data is available only when .+ runs on a server\./)
  } finally { await local.close() }
})

test("with Agent or Human picked, a value opens Session replay narrowed to that kind of its sessions too", async () => {
  const tab = await open()
  try {
    const sources = table(tab.page, WORDS.web.titles.sources)
    const rows = web.tables.sources.find((d) => d.dimension === "channel").rows
    for (const [kind, filter, sessions] of [["Agent", "agent", "agent"], ["Human", "human", "human"], ["All", null, null]]) {
      await sources.getByRole("radio", { name: kind }).click()
      const top = ofKind(rows, (r) => (sessions ? r[sessions] : r.agent + r.human))[0]
      const href = await sources.getByRole("link", { name: WORDS.web.watch(top.value) }).getAttribute("href")
      assert.equal(new URLSearchParams(href.split("?")[1]).get("filter"), filter, kind)
    }
  } finally { await tab.close() }
})

test("a breakdown's Not set and No referrer rows are two rows of their own", async () => {
  const row = { country: null, agent: 1, human: 1, visitors: 2, agent_visitors: 1, human_visitors: 1, page_views: 2, agent_page_views: 1, human_page_views: 1 }
  const sources = web.tables.sources.map((d) => (d.dimension === "referring_domain"
    ? { ...d, rows: [{ ...row, key: null, value: null }, { ...row, key: "", value: "" }] } : d))
  const tab = await open({ webAnswer: { ...web, tables: { ...web.tables, sources } } })
  const warnings = []
  tab.page.on("console", (message) => { if (/same key/i.test(message.text())) warnings.push(message.text()) })
  try {
    const region = table(tab.page, WORDS.web.titles.sources)
    await pick(tab.page, region.getByRole("combobox", { name: `${WORDS.web.titles.sources}: ${WORDS.web.breakdown}` }), WORDS.web.dimensions.referring_domain)
    assert.deepEqual((await cellTexts(region.locator("tbody tr"))).map((cells) => cells[0]).sort(), [WORDS.web.direct, WORDS.web.notSet].sort())
    assert.deepEqual(warnings, [], "each row has a React key of its own")
  } finally { await tab.close() }
})

test("Trends' hover writes each value as its table does: active time in minutes, pages per session with one decimal", async () => {
  const tab = await open()
  try {
    const card = trendsCard(tab.page)
    await card.getByRole("button", { name: WORDS.showAsTable }).click()
    for (const name of ["Active time spent", "Pages per session"]) {
      await pick(tab.page, card.getByRole("combobox", { name: WORDS.metric }), name)
      const surface = await card.locator(".recharts-surface").first().boundingBox()
      await tab.page.mouse.move(surface.x + surface.width / 2, surface.y + surface.height / 2)
      const box = card.locator(".recharts-tooltip-wrapper > div").first()
      await box.waitFor({ state: "visible", timeout: WAIT_MS })
      const [interval, ...said] = (await box.innerText()).split("\n").map((t) => t.trim()).filter(Boolean)
      const row = (await cellTexts(card.locator("table tbody tr"))).find((cells) => cells[0] === interval)
      const values = said.filter((t) => !["Human", "Agent"].includes(t))
      assert.ok(row && values.length, `${name}: the hovered interval ${interval} and its values ${said}`)
      for (const value of values) assert.ok(row.slice(1).includes(value), `${name}: ${value} as the table writes it (${row.slice(1)})`)
      await tab.page.mouse.move(0, 0)
    }
  } finally { await tab.close() }
})
