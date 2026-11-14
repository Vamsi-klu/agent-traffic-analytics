// The replay page in Chromium, against the built app and the recorded samples: the player reads a chunk only
// when it needs it, "Jump to hand-off" lands the API's lead before a hand-off, the cursor carries the name of who acts,
// the timeline's segments sit where the segments say, a replay recorded without its page says so while it has none,
// a chunk that fails can be tried again, and nothing is asked of any other address. Usage: node --test tests/   (npm test)
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { openTab, sample, sessionSample, startApp } from "./app.mjs"

const MIXED = "7f3a-c1" // a human, Claude in Chrome from 0:38, the human again: two hand-offs
const AGENT = "6e0f-13" // 48 s of an agent, five chunks, starts at the beginning
const AUTOMATED = "19fc-90" // 13 s of an automated browser
const FREED = "2b9e-c4" // a human; the replay was deleted to make room, the timeline stays
const HALF_SECOND_MS = 500
const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const range = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => from + i)
const chunkAt = (chunks, ms) => chunks.reduce((found, chunk, n) => (chunk.start_ms <= ms ? n : found), 0)
const chunksAsked = (requests, id) => requests.map((u) => new URL(u)).filter((u) => u.pathname === `/api/session/${id}/replay`)
  .map((u) => Number(u.searchParams.get("chunk"))).sort((a, b) => a - b)
const position = (page) => page.getAttribute("[role=slider]", "aria-valuenow").then(Number)

/** The session page in a fresh tab, once its stage is past loading; `detail` replaces the sample's answer and
 *  `chunk(n, body)` changes each replay chunk's. */
async function open(id, { detail, width, chunk } = {}) {
  const tab = await openTab(app, { width })
  if (detail) await tab.page.route(`**/api/session/${id}`, (route) => route.fulfill({ json: detail }))
  if (chunk) {
    await tab.page.route(`**/api/session/${id}/replay?chunk=*`, async (route) => {
      const response = await route.fetch(), n = Number(new URL(route.request().url()).searchParams.get("chunk"))
      await route.fulfill({ response, json: chunk(n, await response.json()) })
    })
  }
  await tab.page.goto(app.url(`#/sessions/${id}`))
  await tab.page.waitForSelector('[data-replay]:not([data-replay="loading"])', { timeout: WAIT_MS })
  return tab
}

/** Clicks the timeline at a session moment and waits until the replay is there (to the timeline's pixel). */
async function clickTimelineAt(page, ms, durationMs) {
  const bar = await page.$("[data-timeline-bar]")
  await bar.scrollIntoViewIfNeeded() // a note under the stage can push it out of the window
  const { x, y, width } = await bar.evaluate((el) => {
    const box = el.getBoundingClientRect()
    return { x: box.left + el.clientLeft, y: box.top + box.height / 2, width: el.clientWidth }
  })
  await page.mouse.click(x + (width * ms) / durationMs, y)
  const pixelMs = durationMs / width
  await page.waitForFunction(([target, slack]) => Math.abs(Number(document.querySelector("[role=slider]").getAttribute("aria-valuenow")) - target) <= slack,
    [ms, pixelMs], { timeout: WAIT_MS })
}

/** Every value the timeline's position takes from now on, in order (window.positions). */
const notePositions = (page) => page.evaluate(() => {
  const slider = document.querySelector("[role=slider]")
  window.positions = []
  new MutationObserver(() => window.positions.push(Number(slider.getAttribute("aria-valuenow")))).observe(slider, { attributes: true, attributeFilter: ["aria-valuenow"] })
})
const firstPosition = (page) => page.waitForFunction(() => window.positions.length && window.positions[0], undefined, { timeout: WAIT_MS }).then((h) => h.jsonValue())

test("the player opens with the chunks its first moment needs and the next one, and shows the recorded page", async () => {
  const d = sessionSample(AGENT), tab = await open(AGENT)
  try {
    assert.equal(await tab.page.getAttribute("[data-replay]", "data-replay"), "ready")
    assert.deepEqual(chunksAsked(tab.requests, AGENT), range(0, chunkAt(d.replay.chunks, d.replay.start_ms) + 1))
    const shown = await tab.page.frameLocator(".cake-replay iframe").locator("body").innerText()
    assert.match(shown, /Classic T-shirt/, "the stage shows the recorded shop, not a blank frame")
  } finally { await tab.close() }
})

test("a jump reads every chunk up to the moment and one more, and none past that", async () => {
  const d = sessionSample(AGENT), chunks = d.replay.chunks, tab = await open(AGENT)
  try {
    const target = Math.round((chunks[2].start_ms + chunks[2].end_ms) / 2)
    await clickTimelineAt(tab.page, target, d.timeline.duration_ms)
    await tab.page.waitForFunction(() => document.querySelector("[data-replay]").dataset.replay === "ready")
    assert.deepEqual(chunksAsked(tab.requests, AGENT), range(0, chunkAt(chunks, target) + 1))
  } finally { await tab.close() }
})

test("playing reads the next chunk only once playback enters the chunk before it", async () => {
  const d = sessionSample(AGENT), chunks = d.replay.chunks, tab = await open(AGENT)
  try {
    // inside chunk 1: a click on its first millisecond can round into the pause before it, which belongs to chunk 0
    await clickTimelineAt(tab.page, Math.round((chunks[1].start_ms + chunks[1].end_ms) / 2), d.timeline.duration_ms)
    assert.deepEqual(chunksAsked(tab.requests, AGENT), [0, 1, 2])
    await tab.page.locator('[aria-label="Speed"]').getByText("4×").click()
    const third = tab.page.waitForRequest((r) => r.url().endsWith(`/replay?chunk=3`), { timeout: WAIT_MS })
    await tab.page.getByRole("button", { name: "Play" }).click()
    await third
    const at = await position(tab.page)
    assert.ok(at >= chunks[2].start_ms, `chunk 3 was asked for at ${at} ms, before playback reached chunk 2 (${chunks[2].start_ms} ms)`)
    assert.ok(!chunksAsked(tab.requests, AGENT).includes(4), "chunk 4 was asked for too early")
  } finally { await tab.close() }
})

test("Jump to hand-off starts the player the API's lead before the next hand-off, then goes round to the first", async () => {
  const d = sessionSample(MIXED), lead = d.replay.handoff_lead_ms, [first, second] = d.timeline.handoffs
  assert.ok(d.replay.start_ms > first.at_ms && d.replay.start_ms < second.at_ms - lead, "the sample opens between the two hand-offs")
  const tab = await open(MIXED)
  try {
    await notePositions(tab.page)
    await tab.page.getByRole("button", { name: "Jump to hand-off" }).click()
    assert.equal(await firstPosition(tab.page), second.at_ms - lead)
    await tab.page.getByRole("button", { name: "Pause" }).click() // a playing replay moves the position by itself
    await notePositions(tab.page)
    await tab.page.getByRole("button", { name: "Jump to hand-off" }).click()
    assert.equal(await firstPosition(tab.page), first.at_ms - lead)
  } finally { await tab.close() }
})

test("a row of Pages visited starts the player where its page opened, by pointer or by keyboard", async () => {
  const d = sessionSample(MIXED), [, product, cart] = d.pages
  const tab = await open(MIXED)
  try {
    await notePositions(tab.page)
    await tab.page.locator("[data-pages] [data-page-row]").nth(2).click()
    assert.equal(await firstPosition(tab.page), cart.at_ms)
    await tab.page.getByRole("button", { name: "Pause" }).click() // it plays from there, as Jump to hand-off does
    await notePositions(tab.page)
    await tab.page.locator("[data-pages] [data-page-row]").nth(1).getByRole("button").press("Enter")
    assert.equal(await firstPosition(tab.page), product.at_ms)
  } finally { await tab.close() }
})

test("the lead before a hand-off is the API's setting, not a number of the page's own", async () => {
  const d = sessionSample(MIXED), lead = 5000, second = d.timeline.handoffs[1]
  const tab = await open(MIXED, { detail: { ...d, replay: { ...d.replay, handoff_lead_ms: lead } } })
  try {
    await notePositions(tab.page)
    await tab.page.getByRole("button", { name: "Jump to hand-off" }).click()
    assert.equal(await firstPosition(tab.page), second.at_ms - lead)
  } finally { await tab.close() }
})

test("the cursor carries the name of who acts, and the name changes as playback crosses the hand-off", async () => {
  const d = sessionSample(MIXED), first = d.timeline.handoffs[0]
  const tab = await open(MIXED, { detail: { ...d, replay: { ...d.replay, start_ms: 0 } } })
  try {
    await tab.page.getByRole("button", { name: "Jump to hand-off" }).click()
    const human = await tab.page.waitForSelector('.replayer-mouse[data-label="A human"]', { timeout: WAIT_MS })
    assert.equal(await human.getAttribute("data-who"), "human")
    await tab.page.waitForSelector(`.replayer-mouse[data-label="${d.session.agent}"][data-who="agent"]`, { timeout: WAIT_MS })
    assert.ok(await position(tab.page) >= first.at_ms, "the agent's name appeared before the hand-off")
  } finally { await tab.close() }
})

test("the cursor's label is drawn in the colours of who acts, from the theme's tokens", async () => {
  const d = sessionSample(MIXED), tab = await open(MIXED, { detail: { ...d, replay: { ...d.replay, start_ms: 0 } } })
  /** The label's colours when `who` acts, and the colours of that side's soft and text tokens. */
  const drawn = async (who) => {
    await tab.page.waitForSelector(`.replayer-mouse[data-who="${who}"]`, { timeout: WAIT_MS })
    return tab.page.evaluate((side) => {
      const token = (name) => {
        const probe = document.body.appendChild(document.createElement("i"))
        probe.style.color = `var(${name})`
        const colour = getComputedStyle(probe).color
        probe.remove()
        return colour
      }
      const label = getComputedStyle(document.querySelector(".replayer-mouse"), "::before")
      return { drawn: [label.backgroundColor, label.color], tokens: [token(`--${side}-soft`), token(`--${side}-foreground`)] }
    }, who)
  }
  try {
    const human = await drawn("human")
    assert.deepEqual(human.drawn, human.tokens)
    const stretch = d.timeline.segments.find((s) => s.who === "agent")
    await clickTimelineAt(tab.page, Math.round((stretch.start_ms + stretch.end_ms) / 2), d.timeline.duration_ms)
    const agent = await drawn("agent")
    assert.deepEqual(agent.drawn, agent.tokens)
    assert.notDeepEqual(agent.drawn, human.drawn)
  } finally { await tab.close() }
})

for (const [id, width] of [[MIXED, 1280], [MIXED, 485], [AGENT, 1280], [AUTOMATED, 485], [FREED, 1280]]) {
  test(`${id} at ${width} px: the timeline's segments and hand-offs sit within half a second of the API's times`, async () => {
    const d = sessionSample(id), tab = await open(id, { width })
    try {
      const drawn = await tab.page.evaluate(() => {
        const bar = document.querySelector("[data-timeline-bar]"), box = bar.getBoundingClientRect()
        const share = (x) => (x - box.left - bar.clientLeft) / bar.clientWidth
        return {
          segments: [...bar.querySelectorAll("[data-segment]")].map((s) => { const r = s.getBoundingClientRect(); return [share(r.left), share(r.right)] }),
          handoffs: [...document.querySelectorAll("[data-handoff]")].map((h) => share(h.getBoundingClientRect().left)),
        }
      })
      const duration = d.timeline.duration_ms
      assert.equal(drawn.segments.length, d.timeline.segments.length)
      d.timeline.segments.forEach((s, i) => {
        for (const [edge, ms] of [[drawn.segments[i][0], s.start_ms], [drawn.segments[i][1], s.end_ms]]) {
          assert.ok(Math.abs(edge * duration - ms) < HALF_SECOND_MS, `segment ${i} edge drawn at ${Math.round(edge * duration)} ms, the API says ${ms}`)
        }
      })
      d.timeline.handoffs.forEach((h, i) => assert.ok(Math.abs(drawn.handoffs[i] * duration - h.at_ms) < HALF_SECOND_MS, `hand-off ${i}`))
    } finally { await tab.close() }
  })
}

const FULL_SNAPSHOT = 2 // rrweb EventType.FullSnapshot: a whole page
const withoutPages = (body) => ({ ...body, events: body.events.filter((e) => e.type !== FULL_SNAPSHOT) })
const NO_PAGE_NOTE = '[data-replay-note="no-page"]'
const stageElements = (page) => page.evaluate(() => document.querySelector(".cake-replay iframe")?.contentDocument?.body?.querySelectorAll("*").length ?? 0)

test("a replay recorded without its page plays the pointer and says so under the stage, wherever it is", async () => {
  const d = sessionSample(AGENT), tab = await open(AGENT, { chunk: (n, body) => withoutPages(body) })
  try {
    assert.equal(await tab.page.getAttribute("[data-replay]", "data-replay"), "ready")
    await tab.page.waitForSelector(NO_PAGE_NOTE, { timeout: WAIT_MS })
    assert.equal(await stageElements(tab.page), 0, "the stage has no page to show")
    await clickTimelineAt(tab.page, d.replay.chunks.at(-1).start_ms + HALF_SECOND_MS, d.timeline.duration_ms) // the last chunk
    assert.equal(await tab.page.locator(NO_PAGE_NOTE).count(), 1)
  } finally { await tab.close() }
})

test("a replay with its page from the start never shows the note", async () => {
  const d = sessionSample(AGENT), tab = await open(AGENT)
  try {
    assert.ok(await stageElements(tab.page) > 0)
    assert.equal(await tab.page.locator(NO_PAGE_NOTE).count(), 0)
    await clickTimelineAt(tab.page, d.timeline.duration_ms / 2, d.timeline.duration_ms)
    assert.equal(await tab.page.locator(NO_PAGE_NOTE).count(), 0)
  } finally { await tab.close() }
})

test("the note goes once the playhead reaches the first page that was recorded, and the page shows", async () => {
  // the first two chunks lose their pages, so the first page left is chunk 3's
  const d = sessionSample(AGENT), page3 = sample(`replay/${AGENT}/3`).events.find((e) => e.type === FULL_SNAPSHOT)
  const tab = await open(AGENT, { chunk: (n, body) => (n < 2 ? withoutPages(body) : body) })
  try {
    await tab.page.waitForSelector(NO_PAGE_NOTE, { timeout: WAIT_MS })
    await clickTimelineAt(tab.page, page3.timestamp - d.replay.epoch_ms + HALF_SECOND_MS, d.timeline.duration_ms)
    await tab.page.waitForSelector(NO_PAGE_NOTE, { state: "detached", timeout: WAIT_MS })
    assert.ok(await stageElements(tab.page) > 0, "the stage shows the page")
  } finally { await tab.close() }
})

test("a chunk that doesn't come shows what happened and Try again, which then plays", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route(`**/api/session/${AGENT}/replay?chunk=0`, (route) => route.fulfill({ status: 503, json: { error: "Agent Cake is busy." } }))
    await tab.page.goto(app.url(`#/sessions/${AGENT}`))
    await tab.page.waitForSelector('[data-replay="failed"]', { timeout: WAIT_MS })
    assert.match(await tab.page.locator('[data-replay="failed"]').innerText(), /Couldn't load the replay\. Agent Cake is busy\./)
    await tab.page.unroute(`**/api/session/${AGENT}/replay?chunk=0`)
    await tab.page.getByRole("button", { name: "Try again" }).click()
    await tab.page.waitForSelector('[data-replay="ready"]', { timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("playing a replay asks nothing of any address but the page's own", async () => {
  const tab = await open(MIXED)
  try {
    await tab.page.getByRole("button", { name: "Play" }).click()
    await tab.page.waitForFunction(() => Number(document.querySelector("[role=slider]").getAttribute("aria-valuenow")) > 53000, undefined, { timeout: WAIT_MS })
    const elsewhere = tab.requests.filter((u) => !u.startsWith(app.origin) && !u.startsWith("about:") && !u.startsWith("data:"))
    assert.deepEqual(elsewhere, [])
  } finally { await tab.close() }
})
