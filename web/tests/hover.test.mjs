// Every text the interface shows on hover, in one look (DESIGN.md §6, §11), in Chromium against the built app and the
// samples: no page uses the browser's own title box or an SVG <title>; a tooltip's lines start at the left edge, as all
// other text does, in the theme's inverted colours; the charts' hover boxes have the tooltip's colours, corners and text
// size; a hint on a badge or a name opens on keyboard focus where the element stands alone, and on hover inside a
// session row (a link, which has the focus); a filter chip keeps its picked look while its hint is open.
// Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { after, before, test } from "node:test"
import { CLARITY, WORDS } from "../src/lib/words.ts"
import { openTab, sample, scrolled, startApp } from "./app.mjs"

const judging = JSON.parse(readFileSync(new URL("../../agentcake/data/judging.en.json", import.meta.url), "utf8"))
const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** /api/setup with the website's sessions recorded: the sample has none, which shows the onboarding instead. */
const RECORDED = { ...sample("setup"), recorded: { sessions: 9, site: 9, agent: 4 } }
const list = sample("sessions")
const TOTALS = `section[aria-label="${WORDS.totals}"]`
const CHARTS = ".recharts-surface"
const LIST = '[aria-label="Session type"]'
const REPLAY = '[data-replay]:not([data-replay="loading"])'
const tooltip = (page) => page.locator('[data-slot="tooltip-content"]')
const card = (page, title) => page.locator('[data-slot="card"]').filter({ has: page.locator('[data-slot="card-title"]', { hasText: new RegExp(`^${title}$`) }) })

/** A fresh tab at a route, once `ready` is on the page; recorded: answer /api/setup with the website's sessions. */
async function open(route, ready, { recorded = true } = {}) {
  const tab = await openTab(app)
  if (recorded) await tab.page.route("**/api/setup", (r) => r.fulfill({ json: RECORDED }))
  await tab.page.goto(app.url(route))
  await tab.page.locator(ready).first().waitFor({ timeout: WAIT_MS })
  return tab
}

/** What a box's look is made of. */
const look = (locator) => locator.evaluate((el) => {
  const s = getComputedStyle(el)
  return { background: s.backgroundColor, color: s.color, radius: s.borderTopLeftRadius, size: s.fontSize, align: s.textAlign, border: s.borderTopWidth, shadow: s.boxShadow }
})

/** Hover or focus an element (after any scroll has landed: a scroll closes a tooltip), and wait for the tooltip that
 *  says `text`. */
async function hint(page, element, text, how = "hover") {
  await page.keyboard.press("Escape")
  await page.mouse.move(0, 0)
  await element.scrollIntoViewIfNeeded()
  await scrolled(page)
  if (how === "focus") await element.focus()
  else await element.hover()
  const box = tooltip(page).filter({ hasText: text })
  await box.waitFor({ timeout: WAIT_MS })
  return box
}

/** Once the page has run every task queued before this call. React renders an update in a task of its own, posted
 *  through a MessageChannel, which a fake clock leaves alone. */
const handled = (page) => page.evaluate(() => new Promise((done) => {
  const channel = new MessageChannel()
  channel.port1.onmessage = () => done()
  channel.port2.postMessage(null)
}))

/** Moves the pointer between (0, 0) and (1, 1), away from every trigger and tooltip, until no tooltip is open, and
 *  returns how many moves it took. Radix closes a tooltip on a pointer move outside its trigger, the tooltip and the
 *  grace area between them, but watches for that move only once React has handled the move that left the trigger, in
 *  a task of its own. On a busy page a move can come before that task and be lost, so it moves again until the tooltip
 *  closes. The page's clock isn't moved. */
async function moveAwayUntilClosed(page) {
  const until = Date.now() + WAIT_MS
  for (let moves = 1; ; moves++) {
    await page.mouse.move(moves % 2, moves % 2)
    await handled(page)
    if (!(await page.locator('[data-slot="tooltip-content"]:not([data-state="closed"])').count())) return moves
    assert.ok(Date.now() < until, `a tooltip is still open after ${moves} moves away from it`)
  }
}

test("no page uses the browser's own hover box: no title attribute and no SVG <title>", async () => {
  const pages = [["#/dashboard", CHARTS], ["#/sessions", LIST], ["#/sessions?filter=agent", '[aria-label="Human involvement"]'],
    ["#/sessions?filter=human", '[aria-label="Evidence"]'], ["#/sessions/7f3a-c1", REPLAY], ["#/sessions/19fc-90", REPLAY],
    ["#/settings", '[role="progressbar"]'], ["#/components", CHARTS], ["#/", '[data-slot="card"]', { recorded: false }]]
  for (const [route, ready, options] of pages) {
    const tab = await open(route, ready, options)
    try {
      // an empty title shows no box (recharts writes an empty <title> into each chart's SVG)
      const found = await tab.page.evaluate(() => [...document.querySelectorAll("[title], svg title")]
        .filter((el) => (el.tagName.toLowerCase() === "title" ? el.textContent : el.getAttribute("title")).trim()).map((el) => el.outerHTML.slice(0, 160)))
      assert.deepEqual(found, [], route)
    } finally { await tab.close() }
  }
})

test("a tooltip of several lines starts each line at the left edge, in the theme's inverted colours", async () => {
  const tab = await open("#/dashboard", TOTALS)
  try {
    const box = await hint(tab.page, tab.page.getByRole("button", { name: "About Active time spent", exact: true }), CLARITY.activeTime[0], "focus")
    const lines = box.locator("p")
    assert.deepEqual(await lines.allInnerTexts(), CLARITY.activeTime, "one paragraph per line")
    const lefts = await lines.evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().left)))
    assert.equal(new Set(lefts).size, 1, `every line starts at the same left edge, not centred: ${lefts}`)
    const theme = await tab.page.evaluate(() => {
      const probe = document.createElement("span")
      probe.style.color = "var(--foreground)"
      probe.style.backgroundColor = "var(--background)"
      document.body.append(probe)
      const s = getComputedStyle(probe), colours = { foreground: s.color, background: s.backgroundColor }
      probe.remove()
      return colours
    })
    const { background, color, align } = await look(box)
    assert.deepEqual({ background, color, align }, { background: theme.foreground, color: theme.background, align: "left" })
  } finally { await tab.close() }
})

test("the charts' hover boxes look like the tooltips: the same colours, corners, text size and alignment, no frame or shadow", async () => {
  const tab = await open("#/dashboard", CHARTS)
  try {
    const tip = await look(await hint(tab.page, tab.page.getByRole("button", { name: "About Sessions", exact: true }), CLARITY.sessions[0], "focus"))
    await tab.page.keyboard.press("Escape")
    for (const title of [WORDS.agentsChart, WORDS.trends]) {
      const chart = card(tab.page, title)
      await chart.scrollIntoViewIfNeeded()
      await scrolled(tab.page)
      if (title === WORDS.agentsChart) await chart.locator(".recharts-bar-rectangle path").first().hover()
      else {
        const surface = await chart.locator(CHARTS).boundingBox()
        await tab.page.mouse.move(surface.x + surface.width / 2, surface.y + surface.height / 2)
      }
      const box = chart.locator(".recharts-tooltip-wrapper > div").first()
      await box.waitFor({ state: "visible", timeout: WAIT_MS })
      assert.deepEqual(await look(box), tip, title)
    }
  } finally { await tab.close() }
})

test("every tooltip opens after PostHog's 400 ms of hovering, and at once on keyboard focus", async () => {
  const tab = await open("#/dashboard", TOTALS)
  try {
    // the tooltip's delay runs on the page's timers: a fake clock, paused, so only runFor moves it (no waiting)
    await tab.page.clock.install()
    await tab.page.clock.pauseAt(Date.now() + 1000)
    const icon = tab.page.getByRole("button", { name: "About Sessions", exact: true })
    await icon.hover()
    await tab.page.clock.runFor(399)
    await handled(tab.page)  // a tooltip opened by then is on the page
    assert.equal(await tooltip(tab.page).count(), 0, "not yet at 399 ms")
    await tab.page.clock.runFor(1)
    await tooltip(tab.page).filter({ hasText: CLARITY.sessions[0] }).waitFor({ timeout: WAIT_MS })
    // away from the icon and the tooltip: it closes with the clock still paused, so with no close delay
    await moveAwayUntilClosed(tab.page)
    await tooltip(tab.page).first().waitFor({ state: "detached", timeout: WAIT_MS })
    await tab.page.getByRole("button", { name: "About Visitors", exact: true }).focus()
    await tooltip(tab.page).filter({ hasText: WORDS.about.visitors }).waitFor({ timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("every information icon takes the pointer in a 32 px square, and its place in the line stays the icon's", async () => {
  const tab = await open("#/dashboard", TOTALS)
  try {
    const icons = tab.page.locator(TOTALS).getByRole("button")  // the five totals' information icons and the Bot sessions "?"
    assert.equal(await icons.count(), 6)
    for (const icon of await icons.all()) {
      await icon.scrollIntoViewIfNeeded()
      const reach = await icon.evaluate((el) => {
        const box = el.getBoundingClientRect(), x = box.left + box.width / 2, y = box.top + box.height / 2
        const at = (dx, dy) => document.elementFromPoint(x + dx, y + dy)?.closest("button") === el
        return { width: Math.round(box.width), height: Math.round(box.height), edges: [at(-15, 0), at(15, 0), at(0, -15), at(0, 15)], outside: at(17, 0) }
      })
      const name = await icon.getAttribute("aria-label")
      assert.deepEqual({ width: reach.width, height: reach.height }, { width: 14, height: 14 }, `${name}: the line keeps the icon's room`)
      assert.deepEqual(reach.edges, [true, true, true, true], `${name}: 15 px from its centre on every side still takes the pointer`)
      assert.equal(reach.outside, false, `${name}: no more than 32 px`)
    }
  } finally { await tab.close() }
})

test("a badge's or a name's hint opens on keyboard focus where it stands alone: the session page, the Agent block, the top bar", async () => {
  const tab = await open("#/sessions/7f3a-c1", REPLAY)
  try {
    const header = tab.page.locator("h1").locator("xpath=..")
    await hint(tab.page, header.locator('[data-category="human_agent"]').first(), judging.turns.human_agent.about, "focus")
    await hint(tab.page, header.locator('[data-slot="badge"]').filter({ hasText: "Claude in Chrome" }), judging.names.likely.about, "focus")
    await hint(tab.page, tab.page.getByRole("link", { name: /shop\.example\.com/ }), "Open shop.example.com in a new tab", "focus")
  } finally { await tab.close() }
  const unnamed = await open("#/sessions/19fc-90", REPLAY)
  try {
    const header = unnamed.page.locator("h1").locator("xpath=..")
    await hint(unnamed.page, header.locator('[data-slot="badge"]').filter({ hasText: new RegExp(`^${judging.names.unnamed.label}$`) }), judging.names.unnamed.about, "focus")
  } finally { await unnamed.close() }
  const dashboard = await open("#/dashboard", TOTALS)
  try {
    const item = dashboard.page.getByRole("list", { name: WORDS.agentsByName }).locator("li").filter({ hasText: judging.names.unnamed.label })
    await hint(dashboard.page, item.locator("[tabindex]"), judging.names.unnamed.about, "focus")
  } finally { await dashboard.close() }
})

test("inside a session row, a link that has the focus, every hint opens on hover and nothing else takes focus", async () => {
  const tab = await open("#/sessions", LIST)
  try {
    assert.equal(await tab.page.locator('a[href^="#/sessions/"] [tabindex]').count(), 0, "nothing focusable inside a row's link")
    const row = (id) => tab.page.locator(`a[href="#/sessions/${id}"]`)
    for (const [element, text] of [
      [row("7f3a-c1").locator("svg.crumb:not(.avatar)"), WORDS.rowMarker],
      [row("7f3a-c1").locator('[data-slot="badge"]').filter({ hasText: "Claude in Chrome" }), judging.names.likely.about],
      [row("7f3a-c1").locator('[data-category="human_agent"]'), judging.turns.human_agent.about],
      [row("5a7d-3e").locator('[data-slot="badge"]').filter({ hasText: judging.evidence.thin.label }), judging.evidence.thin.about],
      [row("19fc-90").locator('[data-slot="badge"]').filter({ hasText: new RegExp(`^${judging.names.unnamed.label}$`) }), judging.names.unnamed.about],
    ]) await hint(tab.page, element, text)
    assert.equal(await tab.page.getByRole("img", { name: WORDS.rowMarker }).count(), list.results.filter((s) => s.verdict === "agent").length,
      "each Agent row's Crumb is named for screen readers")
  } finally { await tab.close() }
})

test("a filter chip says what it picks on focus, and keeps its picked look while it does", async () => {
  const tab = await open("#/sessions?filter=agent&turns=human_agent", '[aria-label="Human involvement"]')
  try {
    const chip = tab.page.getByRole("radiogroup", { name: "Human involvement" }).getByRole("radio", { name: judging.turns.human_agent.label })
    await hint(tab.page, chip, judging.turns.human_agent.about, "focus")
    assert.equal(await chip.getAttribute("data-state"), "on", "the picked chip stays picked")
    assert.equal(await tab.page.getByRole("radiogroup", { name: "Human involvement" }).getByRole("radio", { name: judging.turns.agent_only.label }).getAttribute("tabindex"), "-1",
      "one chip of the group takes Tab, the arrow keys move between them")
  } finally { await tab.close() }
  const human = await open("#/sessions?filter=human", '[aria-label="Evidence"]')
  try {
    await hint(human.page, human.page.getByRole("radiogroup", { name: "Evidence" }).getByRole("radio", { name: judging.evidence.thin.label }), judging.evidence.thin.about, "focus")
  } finally { await human.close() }
})

test("a long agent name on Top agents shows whole on hover, the warning line on the disk meter says what it marks, the demo shop tag says what it means", async () => {
  const long = "An agent whose name is far too long for two lines on the axis of this chart"
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/setup", (r) => r.fulfill({ json: RECORDED }))
    await tab.page.route("**/api/web**", (r) => r.fulfill({ json: { ...sample("web"), agents: [{ name: long, sessions: 3, visitors: 2, page_views: 4, active_ms: 60000, pages_per_session: 2 }] } }))
    await tab.page.goto(app.url("#/dashboard"))
    const name = card(tab.page, WORDS.agentsChart).locator("foreignObject").getByText(long, { exact: true })
    await name.waitFor({ timeout: WAIT_MS })
    await hint(tab.page, name, long)
  } finally { await tab.close() }
  const settings = await open("#/settings", '[role="progressbar"]')
  try {
    await hint(settings.page, settings.page.locator('[data-warn-line]'), /^Warning threshold: \d+%$/)
  } finally { await settings.close() }
  const overview = await open("#/components", CHARTS)
  try {
    await hint(overview.page, overview.page.locator('[data-slot="badge"]').filter({ hasText: new RegExp(`^${WORDS.demoShop}$`) }).first(), WORDS.demoShopAbout)
  } finally { await overview.close() }
})

