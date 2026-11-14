// The session page around the replay (S5.4) in Chromium, against the built app and the samples: every reason layer is
// shown and one that is off says why, a replay deleted to make room says so while the verdict and timeline stay, a
// replay cut short says so and still plays, the server half has a row per page request, and Pages visited names the
// entry and exit page, then each page in order (at 485 px without scrolling sideways). Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { openTab, sessionSample, startApp } from "./app.mjs"

const MIXED = "7f3a-c1", FREED = "2b9e-c4"
/** The server half's table: the first table outside Pages visited, which comes earlier on the page. */
const SERVER_HALF = "table:not([data-pages] *) >> nth=0"
const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

async function open(id, detail, width) {
  const tab = await openTab(app, { width })
  if (detail) await tab.page.route(`**/api/session/${id}`, (route) => route.fulfill({ json: detail }))
  await tab.page.goto(app.url(`#/sessions/${id}`))
  await tab.page.waitForSelector('[data-replay]:not([data-replay="loading"])', { timeout: WAIT_MS })
  return tab
}

test("all four layers are shown, and the layer that is off shows the reason cake gave", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED)
  try {
    assert.deepEqual(await tab.page.$$eval("[data-layer]", (els) => els.map((el) => el.dataset.layer)), ["name", "verify", "environment", "behavior"])
    const off = d.layers.find((layer) => layer.state === "off")
    const shown = tab.page.locator(`[data-layer="${off.layer}"]`)
    assert.equal(await shown.getAttribute("data-state"), "off")
    assert.match(await shown.innerText(), /Off here/)
    for (const reason of off.reasons) assert.ok((await shown.innerText()).includes(reason.text), reason.text)
  } finally { await tab.close() }
})

test("the verdict and each layer that judged say how sure cake is, bold on the highlighter; thin evidence is marked", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED)
  try {
    const verdict = tab.page.locator("h1").locator("xpath=..").locator('[data-slot="badge"]').first()
    assert.equal((await verdict.innerText()).replace(/\s+/g, " "), `Agent · ${d.percent}%`)
    assert.equal(await verdict.locator("b.bg-highlight").innerText(), `${d.percent}%`)
    for (const layer of d.layers) {
      const badge = (await tab.page.locator(`[data-layer="${layer.layer}"] header`).innerText()).replace(/\s+/g, " ")
      if (layer.percent === null) assert.doesNotMatch(badge, /%/, layer.layer)
      else assert.ok(badge.endsWith(`· ${layer.percent}%`), `${layer.layer}: ${badge}`)
    }
  } finally { await tab.close() }
  const thin = await open(MIXED, { ...d, session: { ...d.session, verdict: "human", evidence: "thin", agent_turns: null, agent: null, certainty: null }, percent: 55 })
  try {
    const badges = thin.page.locator("h1").locator("xpath=..").locator('[data-slot="badge"]')
    assert.equal((await badges.first().innerText()).replace(/\s+/g, " "), "Human · 55%")
    assert.equal((await badges.nth(1).innerText()).trim(), "Thin evidence")
  } finally { await thin.close() }
})

test("a layer that is off with no reason given still says it didn't run", async () => {
  const d = sessionSample(MIXED)
  const layers = d.layers.map((layer) => (layer.state === "off" ? { ...layer, reasons: [] } : layer))
  const tab = await open(MIXED, { ...d, layers })
  try {
    const off = layers.find((layer) => layer.state === "off")
    assert.match(await tab.page.locator(`[data-layer="${off.layer}"]`).innerText(), /This layer didn't run for this session\./)
  } finally { await tab.close() }
})

test("a replay deleted to make room says so, reads no chunk, and keeps the verdict, timeline and server half", async () => {
  const d = sessionSample(FREED), tab = await open(FREED)
  try {
    assert.equal(d.replay.missing, "freed")
    const stage = tab.page.locator("[data-replay]")
    assert.equal(await stage.getAttribute("data-replay"), "missing")
    assert.match(await stage.innerText(), /This replay was deleted to free disk space\. The verdict and the timeline are still here\./)
    assert.equal(tab.requests.filter((u) => u.includes("/replay?chunk=")).length, 0)
    assert.equal(await tab.page.locator("[data-segment]").count(), d.timeline.segments.length)
    assert.equal(await tab.page.locator("[data-layer]").count(), 4)
    assert.equal(await tab.page.locator("[role=slider]").count(), 0, "no position control without a replay")
    assert.equal(await tab.page.getByRole("button", { name: "Play" }).count(), 0)
    const rows = tab.page.locator(SERVER_HALF).locator("tbody tr")
    assert.equal(await rows.count(), d.server.pages.length)
  } finally { await tab.close() }
})

test("a replay cut short while the disk was full says so and plays what is left", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED, { ...d, replay: { ...d.replay, missing: "dropped" } })
  try {
    await tab.page.waitForSelector('[data-replay="ready"]', { timeout: WAIT_MS })
    assert.ok(await tab.page.getByText("Part of this replay wasn't stored because the disk budget was full then.").isVisible())
  } finally { await tab.close() }
})

test("the server half has one row per page request: when, which page, its Sec-Fetch values", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED)
  try {
    const table = tab.page.locator(SERVER_HALF)
    assert.match(await table.locator("thead").innerText(), /cake\.js network match/)
    const rows = await table.locator("tbody tr").evaluateAll((trs) => trs.map((tr) => [...tr.querySelectorAll("td")].map((td) => td.innerText)))
    assert.deepEqual(rows.map((cells) => cells[1]), d.server.pages.map((p) => p.path))
    assert.deepEqual(rows.map((cells) => cells[2]), d.server.pages.map((p) => [p.fetch.site, p.fetch.mode, p.fetch.dest, p.fetch.user].map((v) => v ?? "—").join(" · ")))
  } finally { await tab.close() }
})

test("a session without server-half rows says why, in cake's words", async () => {
  const d = sessionSample(MIXED), note = "Your site's server sends no notes yet: Settings shows how to add them."
  const tab = await open(MIXED, { ...d, server: { pages: [], network: null, note } })
  try {
    assert.ok(await tab.page.getByText(note).isVisible())
  } finally { await tab.close() }
})

/** Each row of Pages visited as its cells' text, and who acted there (the badge's category). */
const pageRows = (page) => page.locator("[data-pages] [data-page-row]").evaluateAll((trs) => trs.map((tr) => ({
  cells: [...tr.querySelectorAll("td")].map((td) => td.innerText), who: tr.querySelector("[data-slot=badge]")?.dataset.category ?? null })))

test("Pages visited names the entry and exit page, then each page in order: when, how long, who acted, its actions", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED)
  try {
    const ends = await tab.page.locator("[data-pages] dl > div").evaluateAll((divs) => divs.map((div) => div.innerText.replace(/\s+/g, " ")))
    assert.deepEqual(ends, [`Entry page ${d.pages[0].path}`, `Exit page ${d.pages.at(-1).path}`])
    const rows = await pageRows(tab.page)
    assert.deepEqual(rows.map((row) => row.cells[0]), ["0:00", "0:21", "1:06", "1:10"])
    assert.deepEqual(rows.map((row) => row.cells[1]), d.pages.map((p) => p.path))
    assert.deepEqual(rows.map((row) => row.cells[2]), ["21s", "44s", "4s", "26s"])
    assert.deepEqual(rows.map((row) => row.who), d.pages.map((p) => p.who))
    assert.deepEqual(rows.map((row) => row.cells[4]), d.pages.map((p) => String(p.actions)))
  } finally { await tab.close() }
})

test("without a replay to move, the rows of Pages visited are no buttons, and a page without actions says 0 and names nobody", async () => {
  const d = sessionSample(FREED), tab = await open(FREED)
  try {
    assert.equal(await tab.page.locator("[data-pages] tbody").getByRole("button").count(), 0)
    const rows = await pageRows(tab.page)
    assert.equal(rows.length, d.pages.length)
    assert.equal(rows.at(-1).cells[4], "0")
    assert.equal(d.pages.at(-1).who, null)
    assert.deepEqual([rows.at(-1).who, rows.at(-1).cells[3]], [null, "—"])
  } finally { await tab.close() }
})

test("at 485 px Pages visited fits without scrolling sideways and leaves out the Actions column", async () => {
  const tab = await open(MIXED, undefined, 485)
  try {
    const table = tab.page.locator("[data-pages] [data-slot=table-container]")
    const { scroll, client } = await table.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }))
    assert.ok(scroll <= client, `the table is ${scroll} px wide in ${client} px`)
    assert.equal(await tab.page.locator("[data-pages] thead").getByText("Actions").isVisible(), false)
  } finally { await tab.close() }
})
