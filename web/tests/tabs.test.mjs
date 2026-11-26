// A session of more than one tab in Chromium, against the built app and the samples (src/data/fixtures/session/4c2d-71:
// two recorded replays, the second tab opening 20 s in; scripts/tab-sample.mjs): its row says how many tabs and draws a
// line per tab; its page says how many, has a track per tab, names the tab on the stage, has the tab menu and a Tab
// column in its tables, and shows each tab's own reasons. Following the visitor, the replay moves to the second tab's
// replay where the agent there acts, reading its chunks with ?tab=; picking a tab shows it at the same moment; an
// address that named a tab opens with it picked. A session of one tab shows none of it and asks no tab. Usage:
// node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { openTab, sessionSample, startApp } from "./app.mjs"

const TABS = "4c2d-71", SECOND = "a1b8-20", ONE_TAB = "7f3a-c1"
const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** The session page in a fresh tab, once its stage is past loading; `detail` replaces the sample's answer. */
async function open(id, { detail, width } = {}) {
  const tab = await openTab(app, { width })
  if (detail) await tab.page.route(`**/api/session/${id}`, (route) => route.fulfill({ json: detail }))
  await tab.page.goto(app.url(`#/sessions/${id}`))
  await tab.page.waitForSelector('[data-replay]:not([data-replay="loading"])', { timeout: WAIT_MS })
  return tab
}

/** The tab each chunk request of a session asked for (null: none). */
const tabsAsked = (requests, id) => requests.map((u) => new URL(u)).filter((u) => u.pathname === `/api/session/${id}/replay`)
  .map((u) => u.searchParams.get("tab"))
const stageTab = (page) => page.locator("[data-stage-tab]").innerText()
const position = (page) => page.getAttribute("[role=slider]", "aria-valuenow").then(Number)

/** Clicks the first track at a session moment and waits until the replay is there. */
async function clickTimelineAt(page, ms, durationMs) {
  const bar = page.locator("[data-timeline-bar]").first()
  await bar.scrollIntoViewIfNeeded()
  const { x, y, width } = await bar.evaluate((el) => {
    const box = el.getBoundingClientRect()
    return { x: box.left + el.clientLeft, y: box.top + box.height / 2, width: el.clientWidth }
  })
  await page.mouse.click(x + (width * ms) / durationMs, y)
  await page.waitForFunction(([target, slack]) => Math.abs(Number(document.querySelector("[role=slider]").getAttribute("aria-valuenow")) - target) <= slack,
    [ms, durationMs / width], { timeout: WAIT_MS })
}

/** Picks an item of a Select by the Select's name and the item's text. */
async function pick(page, name, item) {
  await page.getByRole("combobox", { name }).click()
  await page.getByRole("option", { name: item, exact: true }).click()
}

test("the list's row of a session of two tabs says so and draws a line per tab", async () => {
  const { page, close } = await openTab(app)
  try {
    await page.goto(app.url("#/sessions"))
    const row = page.locator(`a[href="#/sessions/${TABS}"]`)
    await row.waitFor({ timeout: WAIT_MS })
    assert.match(await row.innerText(), /2 tabs · 8 pages · /)
    assert.equal(await row.locator('[aria-label^="Tab "]').count(), 2)
    assert.equal(await page.locator(`a[href="#/sessions/${ONE_TAB}"]`).getByText(/tabs ·/).count(), 0, "a session of one tab")
  } finally {
    await close()
  }
})

test("its page says how many tabs, has a track per tab, the tab menu and a Tab column in its tables", async () => {
  const detail = sessionSample(TABS)
  const { page, close } = await open(TABS)
  try {
    assert.match(await page.locator("h1 + p").innerText(), / · 2 tabs · 8 pages · /)
    assert.deepEqual(await page.locator("[data-tab-label]").allInnerTexts(), ["Tab 1", "Tab 2"])
    assert.equal(await page.locator("[data-timeline-bar]").count(), 2)
    assert.equal(await page.getByRole("combobox", { name: "Tab shown in the replay" }).innerText(), "Follow the visitor")
    assert.deepEqual(await page.locator("[data-pages] [data-tab-cell]").allInnerTexts(), detail.pages.map((p) => String(p.tab)))
    assert.equal(await page.locator("[data-tab-cell]").count(), detail.pages.length + detail.actions.length + detail.server.pages.length)
  } finally {
    await close()
  }
})

test("following the visitor, the replay shows the tab acted in at each moment, each read with its ?tab=", async () => {
  const detail = sessionSample(TABS)
  const { page, requests, close } = await open(TABS)
  const shows = async (ms, tab) => {
    await clickTimelineAt(page, ms, detail.timeline.duration_ms)
    await page.waitForFunction((name) => document.querySelector("[data-stage-tab]")?.textContent === name, tab, { timeout: WAIT_MS })
    await page.waitForSelector('[data-replay="ready"]', { timeout: WAIT_MS })
    assert.equal(await page.locator("[data-tab-label][data-shown]").innerText(), tab)
    assert.ok(Math.abs((await position(page)) - ms) < 1000, "at the same moment of the session")
  }
  try {
    await shows(5_000, "Tab 1") // before the second tab opens
    await shows(30_000, "Tab 2") // its agent acts there
    await shows(80_000, "Tab 1") // the second tab is closed: the first again
    assert.deepEqual([...new Set(tabsAsked(requests, TABS))].sort(), [detail.tabs[0].id, SECOND].sort())
  } finally {
    await close()
  }
})

test("picking a tab in the menu shows that tab at the same moment, and following again goes back", async () => {
  const detail = sessionSample(TABS)
  const { page, close } = await open(TABS)
  try {
    await clickTimelineAt(page, 30_000, detail.timeline.duration_ms)
    await page.waitForFunction(() => document.querySelector("[data-stage-tab]")?.textContent === "Tab 2", null, { timeout: WAIT_MS })
    await pick(page, "Tab shown in the replay", "Tab 1")
    await page.waitForFunction(() => document.querySelector("[data-stage-tab]")?.textContent === "Tab 1", null, { timeout: WAIT_MS })
    assert.ok(Math.abs((await position(page)) - 30_000) < 1000)
    await pick(page, "Tab shown in the replay", "Follow the visitor")
    await page.waitForFunction(() => document.querySelector("[data-stage-tab]")?.textContent === "Tab 2", null, { timeout: WAIT_MS })
  } finally {
    await close()
  }
})

test("why this classification opens on the tab the verdict rests on, and the other tab shows its own", async () => {
  const detail = sessionSample(TABS)
  const { page, close } = await open(TABS)
  try {
    const reasons = page.getByRole("radiogroup", { name: "Tab classified" })
    assert.equal(await reasons.getByRole("radio", { checked: true }).innerText(), "Tab 1")
    assert.ok((await page.getByText(detail.tabs[0].summary).count()) > 0)
    await reasons.getByRole("radio", { name: "Tab 2" }).click()
    await page.getByText(detail.tabs[1].summary).waitFor({ timeout: WAIT_MS })
  } finally {
    await close()
  }
})

test("an address that named one of its tabs opens with that tab picked, on the stage and in the reasons", async () => {
  const detail = { ...sessionSample(TABS), named_tab: SECOND }
  const { page, close } = await open(TABS, { detail })
  try {
    assert.equal(await stageTab(page), "Tab 2")
    assert.equal(await page.getByRole("combobox", { name: "Tab shown in the replay" }).innerText(), "Tab 2")
    assert.equal(await page.getByRole("radiogroup", { name: "Tab classified" }).getByRole("radio", { checked: true }).innerText(), "Tab 2")
  } finally {
    await close()
  }
})

test("the address of a tab's later part opens the replay where that part starts, not at the tab's first part", async () => {
  const sample = sessionSample(TABS)
  const later = { ...sample.tabs[1], tab: 1 } // one tab in two parts: it went quiet in between, and went on
  const detail = { ...sample, tabs: [sample.tabs[0], later], named_tab: SECOND }
  const { page, close } = await open(TABS, { detail })
  try {
    assert.ok(Math.abs((await position(page)) - later.replay.start_ms) < 1000, `opened at ${await position(page)}`)
  } finally {
    await close()
  }
})

test("a session of several tabs whose replays were all deleted has no replay controls, as one tab has none", async () => {
  const sample = sessionSample(TABS)
  const freed = (replay) => ({ ...replay, chunks: [], missing: "freed" })
  const detail = { ...sample, replay: freed(sample.replay), tabs: sample.tabs.map((tab) => ({ ...tab, replay: freed(tab.replay) })) }
  const tab = await openTab(app)
  try {
    await tab.page.route(`**/api/session/${TABS}`, (route) => route.fulfill({ json: detail }))
    await tab.page.goto(app.url(`#/sessions/${TABS}`))
    await tab.page.waitForSelector('[data-replay="missing"]', { timeout: WAIT_MS })
    assert.equal(await tab.page.getByRole("button", { name: "Play" }).count(), 0)
  } finally {
    await tab.close()
  }
})

test("a session of one tab has no tab menu, no tab on the stage, no Tab column and asks for no tab", async () => {
  const { page, requests, close } = await open(ONE_TAB)
  try {
    for (const selector of ["[data-stage-tab]", "[data-tab-label]", "[data-tab-cell]"]) assert.equal(await page.locator(selector).count(), 0, selector)
    assert.equal(await page.getByRole("combobox", { name: "Tab shown in the replay" }).count(), 0)
    assert.equal(await page.getByRole("radiogroup", { name: "Tab classified" }).count(), 0)
    assert.ok(tabsAsked(requests, ONE_TAB).length > 0 && tabsAsked(requests, ONE_TAB).every((tab) => tab === null))
  } finally {
    await close()
  }
})

test("at 485 px the page of a session of two tabs scrolls only down", async () => {
  const { page, close } = await open(TABS, { width: 485 })
  try {
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  } finally {
    await close()
  }
})
