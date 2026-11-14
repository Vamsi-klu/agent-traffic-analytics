// The dashboard (S5.3) in Chromium, against the built app and the sample /api/overview and /api/setup: the Agent block
// with its split and each agent by name (D39), the average session length (D30, one cell per kind of visitor), the Disk bar and its
// warning, the top block before the first Agent session, the two page tables, the coverage note and the session
// categories. Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { after, before, test } from "node:test"
import { duration, mbToBytes, percent } from "../src/lib/format.ts"
import { openTab, sample, startApp } from "./app.mjs"

const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const overview = sample("overview"), setup = sample("setup")
const judging = JSON.parse(readFileSync(new URL("../../agentcake/data/judging.en.json", import.meta.url), "utf8"))
const RECORDED = { ...setup, recorded: { sessions: 9, agent: 4 } }
/** The sample answer with no Agent session in its range. */
const NO_AGENTS = { ...overview, counts: { ...overview.counts, agent: 0, agent_only: 0, human_agent: 0 }, latest_agent: [], agents_seen: [] }

/** setupAnswer: /api/setup's answer, by default one with sessions recorded (with nothing recorded the dashboard is the
 *  onboarding, D37). */
async function open({ answer, setupAnswer = RECORDED, width } = {}) {
  const tab = await openTab(app, { width })
  if (answer) await tab.page.route("**/api/overview**", (route) => route.fulfill({ json: answer }))
  await tab.page.route("**/api/setup", (route) => route.fulfill({ json: setupAnswer }))
  await tab.page.goto(app.url("#/dashboard"))
  if (setupAnswer.recorded.sessions > 0) await tab.page.getByRole("region", { name: "Average session length" }).waitFor({ timeout: WAIT_MS })
  return tab
}

test("the Agent block counts Agent sessions, split into Agent only and Human + agent, and lists each agent by name", async () => {
  const tab = await open()
  try {
    const block = tab.page.locator('[aria-labelledby="spot-title"]')
    const text = (await block.innerText()).replace(/\s+/g, " ")
    for (const group of ["agent_only", "human_agent"]) assert.ok(text.includes(`${overview.counts[group]} ${judging.turns[group].label}`), group)
    assert.equal(await block.locator('a[href="#/sessions?filter=agent&turns=human_agent"]').count(), 1)
    const names = (await block.getByRole("list", { name: "Agents by name" }).locator("li").allInnerTexts()).map((t) => t.replace(/\s+/g, " ").trim())
    assert.deepEqual(names, overview.agents_seen.map((a) => `${a.sessions} ${a.name ?? judging.names.unnamed.label}`))
    const named = overview.agents_seen.find((a) => a.name)
    assert.equal(await block.locator(`a[href="#/sessions?filter=agent&agent=${encodeURIComponent(named.name)}"]`).count(), 1)
    assert.doesNotMatch(text, /AI in a real browser|Automated browser/, "D39: no kinds of agent")
  } finally { await tab.close() }
})

test("the average session length has one cell each for Human, Agent only and Human + agent (D30)", async () => {
  const tab = await open()
  try {
    const region = tab.page.getByRole("region", { name: "Average session length" })
    assert.ok(await region.getByText(overview.average_length.about).isVisible())
    const cells = (await region.locator('[data-slot="card"]').allInnerTexts()).map((t) => t.split("\n").map((s) => s.trim()).filter(Boolean))
    const { ms } = overview.average_length, { verdicts, turns } = judging
    assert.deepEqual(cells.map((c) => c.slice(0, 2)), [
      [verdicts.human.label, duration(ms.human)],
      [turns.agent_only.label, duration(ms.agent_only)],
      [turns.human_agent.label, duration(ms.human_agent)],
    ])
  } finally { await tab.close() }
})

test("a kind of visitor with no session in the range shows a dash, not a length", async () => {
  const answer = { ...overview, average_length: { ...overview.average_length, ms: { ...overview.average_length.ms, human_agent: null } } }
  const tab = await open({ answer })
  try {
    const turns = tab.page.getByRole("region", { name: "Average session length" }).locator('[data-slot="card"]').last()
    assert.match(await turns.innerText(), /^Human \+ agent\s+—\s+No sessions in this range$/)
  } finally { await tab.close() }
})

test("the Human number says how many of its sessions are on thin evidence (D39: no Unknown)", async () => {
  const tab = await open()
  try {
    const cards = (await tab.page.locator('[data-slot="card"]').allInnerTexts()).map((t) => t.replace(/\s+/g, " "))
    const want = `${judging.verdicts.human.label} ${overview.counts.human} ${overview.counts.thin} with thin evidence`
    assert.ok(cards.some((t) => t.startsWith(want)), cards.slice(0, 6).join(" | "))
    assert.ok(!cards.some((t) => t.startsWith("Unknown ")), "no Unknown number")
  } finally { await tab.close() }
})

test("the Disk bar shows the use of the budget, and warns from warn_at_pct with what happens when it is full", async () => {
  const { storage } = overview, budget = mbToBytes(storage.budget_mb)
  let tab = await open()
  try {
    const disk = tab.page.getByRole("region", { name: "Disk" })
    assert.ok(await disk.getByRole("progressbar", { name: `Disk used ${percent(storage.used_bytes, budget)}%` }).isVisible())
    assert.equal(await disk.getByRole("alert").count(), 0, "no warning below warn_at_pct")
  } finally { await tab.close() }
  const nearlyFull = Math.ceil((budget * (storage.warn_at_pct + 5)) / 100)
  for (const autoFree of [true, false]) {
    tab = await open({ answer: { ...overview, storage: { ...storage, used_bytes: nearlyFull, auto_free: autoFree } } })
    try {
      const warning = tab.page.getByRole("region", { name: "Disk" }).getByRole("alert")
      assert.match(await warning.innerText(), new RegExp(`You've used ${storage.warn_at_pct + 5}% of the disk budget\\.`))
      assert.match(await warning.innerText(), autoFree ? /replays of Human sessions/ : /stops storing new replays/)
    } finally { await tab.close() }
  }
})

test("with nothing recorded, the dashboard shows how to connect the website (D37, D40), not a separate block", async () => {
  assert.equal(setup.recorded.sessions, 0)
  const tab = await open({ answer: NO_AGENTS, setupAnswer: setup })
  try {
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.getByRole("heading", { name: "Dashboard", level: 1 }).count(), 0)
    assert.equal(await tab.page.getByRole("combobox", { name: "Source" }).count(), 0)
  } finally { await tab.close() }
})

test("before the first Agent session the top block says none came yet, without a task or examples", async () => {
  const tab = await open({ answer: NO_AGENTS, setupAnswer: { ...setup, recorded: { sessions: 3, agent: 0 } } })
  try {
    await tab.page.getByText("No agent has visited yet").waitFor({ timeout: WAIT_MS })
    assert.ok(await tab.page.getByText("When an AI agent visits your website, its session shows up here first.").isVisible())
    assert.equal(await tab.page.getByText("Example data", { exact: true }).count(), 0)
    assert.equal(await tab.page.getByRole("combobox", { name: "Source" }).count(), 0, "D40: no source filter")
  } finally { await tab.close() }
})

test("with Agent sessions only outside the filters, the top block keeps its numbers", async () => {
  const tab = await open({ answer: NO_AGENTS, setupAnswer: { ...setup, recorded: { sessions: 9, agent: 4 } } })
  try {
    await tab.page.getByRole("heading", { name: "Sessions where an AI agent acted for a human" }).waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.getByText("No agent has visited yet").count(), 0)
  } finally { await tab.close() }
})

test("pages agents and humans visit most: one list in two orders, side by side when wide, stacked at 485", async () => {
  for (const [width, sideBySide] of [[1280, true], [485, false]]) {
    const tab = await open({ width })
    try {
      const boxes = []
      for (const [title, by] of [["Pages agents visit most", "agent"], ["Pages humans visit most", "human"]]) {
        const region = tab.page.getByRole("region", { name: title })
        boxes.push(await region.boundingBox())
        const paths = await region.locator("tbody tr td:first-child").allInnerTexts()
        const want = [...overview.top_pages].sort((a, b) => b[by] - a[by]).map((p) => p.path)
        assert.deepEqual(paths, want, `${title} at ${width}`)
      }
      const [agents, humans] = boxes
      if (sideBySide) assert.ok(Math.abs(agents.y - humans.y) < 1 && humans.x > agents.x, "side by side")
      else assert.ok(humans.y >= agents.y + agents.height, "stacked")
    } finally { await tab.close() }
  }
})

test("the coverage note has its three columns and every row of /api/overview, on a phone too", async () => {
  const tab = await open({ width: 485 })
  try {
    const { coverage } = overview
    const table = tab.page.getByLabel(coverage.title).locator("table")
    assert.deepEqual(await table.locator("thead th").allInnerTexts(), [coverage.columns.what, coverage.columns.shown_as, coverage.columns.how])
    assert.deepEqual(await table.locator("tbody tr td:first-child").allInnerTexts(), coverage.rows.map((r) => r.what))
    const [scroll, client] = await tab.page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
    assert.ok(scroll <= client, "no horizontal scroll")
  } finally { await tab.close() }
})

test("the session categories list each verdict (no Unknown) and Agent's two kinds, aligned, one badge shape, on a phone too", async () => {
  const tab = await open({ width: 485 })
  try {
    const table = tab.page.getByLabel(judging.title).locator("table")
    const rows = (await table.locator("tr").allInnerTexts()).map((t) => t.replace(/\s+/g, " ").trim())
    const { verdicts, turns } = judging
    assert.deepEqual(rows, [
      `${verdicts.human.label} ${verdicts.human.about}`, `${verdicts.agent.label} ${verdicts.agent.about}`,
      `${turns.agent_only.label} ${turns.agent_only.about}`, `${turns.human_agent.label} ${turns.human_agent.about}`,
      `${verdicts.bot.label} ${verdicts.bot.about}`,
    ])
    const badges = await table.locator('[data-slot="badge"]').evaluateAll((els) => els.map((el) => {
      const box = el.getBoundingClientRect(), cell = el.closest("td").getBoundingClientRect(), style = getComputedStyle(el)
      return { left: Math.round(box.left - cell.left), height: Math.round(box.height), border: style.borderStyle, radius: style.borderRadius }
    }))
    assert.equal(badges.length, 5)
    assert.equal(new Set(badges.map((b) => JSON.stringify(b))).size, 1, `one shape, all left-aligned: ${JSON.stringify(badges)}`)
    const [scroll, client] = await tab.page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
    assert.ok(scroll <= client, "no horizontal scroll")
  } finally { await tab.close() }
})

test("the dashboard's words name visitors Human or Agent and name no other product", async () => {
  const tab = await open()
  try {
    // "user agent" is the HTTP header, not a visitor (DESIGN.md §2; check:ui's rule for the samples)
    assert.doesNotMatch(await tab.page.locator("body").innerText(), /PostHog|\bperson\b|\bpeople\b|\busers?\b(?![ -]agent)/i)
  } finally { await tab.close() }
})
