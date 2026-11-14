// The session list (S5.4) in Chromium, against the built app and the sample list: the pinned Agent filter sits at the far
// left and the other chips are All and D39's verdicts, Agent rows stand out and bot rows are muted, under Agent the split
// (Agent only, Human + agent) combines with the agent's name (a link to one name shows that agent), and the agent and
// date filters reach the API. Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { after, before, test } from "node:test"
import { openTab, sample, startApp } from "./app.mjs"

const judging = JSON.parse(readFileSync(new URL("../../agentcake/data/judging.en.json", import.meta.url), "utf8"))

const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const list = sample("sessions")
const ids = (page) => page.$$eval('a[href^="#/sessions/"]', (rows) => rows.map((row) => row.getAttribute("href").split("/").pop()))
const sessionsAsked = (requests) => requests.map((u) => new URL(u)).filter((u) => u.pathname === "/api/sessions").map((u) => Object.fromEntries(u.searchParams))

async function open(query = "") {
  const tab = await openTab(app)
  await tab.page.goto(app.url(`#/sessions${query}`))
  await tab.page.waitForSelector('[aria-label="Verdict"]', { timeout: WAIT_MS })
  return tab
}

test("the chips are the pinned Agent, then All and the other verdicts, each with its count", async () => {
  const tab = await open()
  try {
    const chips = (await tab.page.locator('[aria-label="Verdict"] > *').allInnerTexts()).map((t) => t.replace(/\s+/g, " "))
    const { verdicts } = judging
    assert.deepEqual(chips, [`${verdicts.agent.label} ${list.counts.agent}`, `All ${list.counts.all}`, `${verdicts.human.label} ${list.counts.human}`,
      `${verdicts.bot.label} ${list.counts.bot}`])
  } finally { await tab.close() }
})

test("Agent is the first filter, and it keeps the Agent rows, every one highlighted", async () => {
  const tab = await open()
  try {
    const chips = tab.page.locator('[aria-label="Verdict"] > *')
    await chips.first().click()
    await tab.page.waitForURL(/filter=agent/)
    await tab.page.waitForFunction((n) => document.querySelectorAll('a[href^="#/sessions/"]').length === n, list.results.filter((s) => s.verdict === "agent").length)
    const rows = await tab.page.$$eval('a[href^="#/sessions/"]', (els) => els.map((el) => el.dataset.highlight))
    assert.ok(rows.every((h) => h === "true"), "every Agent row is highlighted")
  } finally { await tab.close() }
})

test("under Agent, the split and the agent's name combine and reach /api/sessions; no kind of agent (D39)", async () => {
  const tab = await open("?filter=agent")
  try {
    assert.equal(await tab.page.locator('[aria-label="Kind of agent"]').count(), 0)
    const asked = tab.page.waitForRequest((r) => {
      const u = new URL(r.url())
      return u.pathname === "/api/sessions" && u.searchParams.get("turns") === "human_agent" && u.searchParams.get("agent") === "Claude in Chrome"
    }, { timeout: WAIT_MS })
    await tab.page.locator('[aria-label="Human involvement"]').getByText(judging.turns.human_agent.label).click()
    await tab.page.waitForURL(/turns=human_agent/)
    await tab.page.getByRole("combobox", { name: "Agent" }).click()
    await tab.page.getByRole("option", { name: "Claude in Chrome" }).click()
    await asked
    const want = list.results.filter((s) => s.agent_turns === "human_agent" && s.agent === "Claude in Chrome").map((s) => s.id)
    await tab.page.waitForFunction((n) => document.querySelectorAll('a[href^="#/sessions/"]').length === n, want.length)
    assert.deepEqual(await ids(tab.page), want)
  } finally { await tab.close() }
})

test("under Human, the thin evidence filter keeps the sessions cake couldn't tell, each marked", async () => {
  const tab = await open("?filter=human")
  try {
    const asked = tab.page.waitForRequest((r) => {
      const u = new URL(r.url())
      return u.pathname === "/api/sessions" && u.searchParams.get("verdict") === "human" && u.searchParams.get("evidence") === "thin"
    }, { timeout: WAIT_MS })
    await tab.page.locator('[aria-label="Evidence"]').getByText(judging.evidence.thin.label).click()
    await tab.page.waitForURL(/evidence=thin/)
    await asked
    const want = list.results.filter((s) => s.verdict === "human" && s.evidence === "thin").map((s) => s.id)
    await tab.page.waitForFunction((n) => document.querySelectorAll('a[href^="#/sessions/"]').length === n, want.length)
    assert.deepEqual(await ids(tab.page), want)
    for (const row of await tab.page.$$('a[href^="#/sessions/"]')) assert.match(await row.innerText(), new RegExp(judging.evidence.thin.label))
  } finally { await tab.close() }
})

test("bot rows are muted and say there is no human behind them", async () => {
  const tab = await open("?filter=bot")
  try {
    const bots = list.results.filter((s) => s.verdict === "bot").map((s) => s.id)
    await tab.page.waitForFunction((n) => document.querySelectorAll('a[href^="#/sessions/"]').length === n, bots.length)
    assert.deepEqual(await ids(tab.page), bots)
    for (const row of await tab.page.$$('a[href^="#/sessions/"]')) {
      assert.match(await row.innerText(), /No human behind it · counted only/)
      assert.equal(await row.getAttribute("data-highlight"), null)
    }
  } finally { await tab.close() }
})

test("a link to one agent's name shows that agent's sessions, with the pinned filter on", async () => {
  const tab = await open(`?filter=agent&agent=${encodeURIComponent("Meta Muse")}`)
  try {
    assert.equal(await tab.page.locator('[aria-label="Verdict"] > *').first().getAttribute("data-state"), "on")
    await tab.page.waitForFunction(() => document.querySelectorAll('a[href^="#/sessions/"]').length === 1)
    assert.deepEqual(await ids(tab.page), list.results.filter((s) => s.agent === "Meta Muse").map((s) => s.id))
  } finally { await tab.close() }
})

test("an unnamed agent's row says Unnamed, with no avatar; a named one gives how sure its name is inside its name's tag", async () => {
  const tab = await open("?filter=agent")
  try {
    const unnamed = list.results.find((s) => s.verdict === "agent" && !s.agent)
    const named = list.results.find((s) => s.verdict === "agent" && s.agent && s.certainty)
    await tab.page.waitForSelector(`a[href$="/${unnamed.id}"]`, { timeout: WAIT_MS })
    const row = tab.page.locator(`a[href$="/${unnamed.id}"]`)
    assert.match(await row.innerText(), new RegExp(judging.names.unnamed.label))
    assert.equal(await row.locator("svg.avatar").count(), 0)
    assert.match(await tab.page.locator(`a[href$="/${named.id}"] [data-slot=badge]`).filter({ hasText: named.agent }).innerText(),
      new RegExp(`${named.agent}\\s*·\\s*${judging.names[named.certainty].label.toLowerCase()}`))
  } finally { await tab.close() }
})

test("the agent and date filters reach /api/sessions and narrow the rows; there is no source filter (D40)", async () => {
  const tab = await open()
  try {
    await tab.page.getByRole("combobox", { name: "Agent" }).click()
    await tab.page.getByRole("option", { name: "Meta Muse" }).click()
    await tab.page.waitForFunction(() => document.querySelectorAll('a[href^="#/sessions/"]').length === 1)
    assert.deepEqual(await ids(tab.page), list.results.filter((s) => s.agent === "Meta Muse").map((s) => s.id))
    // The list already has one row, so wait for the request itself: on a busy machine it can come after the URL changes.
    const askedToday = tab.page.waitForRequest((r) => {
      const u = new URL(r.url())
      return u.pathname === "/api/sessions" && u.searchParams.get("agent") === "Meta Muse" && u.searchParams.get("range") === "today"
    }, { timeout: WAIT_MS })
    await tab.page.getByRole("combobox", { name: "Date" }).click()
    await tab.page.getByRole("option", { name: "Today" }).click()
    await tab.page.waitForURL(/range=today/)
    await askedToday
    await tab.page.waitForFunction(() => document.querySelectorAll('a[href^="#/sessions/"]').length === 1)
    assert.ok(sessionsAsked(tab.requests).some((q) => q.agent === "Meta Muse" && q.range === "today"))
    assert.equal(await tab.page.getByRole("combobox", { name: "Source" }).count(), 0)
  } finally { await tab.close() }
})
