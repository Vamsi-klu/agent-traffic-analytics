// shoot() (scripts/shots.mjs), which the visual baseline, the screenshots and these tests open pages with, hands over
// the page drawn: also when the page's own requests start after the network has been quiet for longer than the 500 ms
// a quiet network is waited for, as on a busy machine between the answer to whether this AgentCake registered and the
// page's own requests. Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { startApp } from "./app.mjs"
import { pickStyle, shoot } from "../scripts/shots.mjs"

/** How long the page holds its overview request back: longer than Playwright's networkidle waits for quiet. */
const HELD_BACK_MS = 1500
let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** How many elements the component overview has once shoot() hands it over, its overview request held back `heldMs`. */
async function overviewElements(heldMs) {
  const context = await app.browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light", reducedMotion: "reduce" })
  await pickStyle(context, "minimal")
  await context.addInitScript((ms) => {
    const send = window.fetch.bind(window)
    window.fetch = (input, init) => (ms && new URL(String(input), location.href).pathname.endsWith("/api/overview")
      ? new Promise((wait) => setTimeout(wait, ms)).then(() => send(input, init))
      : send(input, init))
  }, heldMs)
  try {
    const page = await context.newPage()
    await shoot(page, app.url("#/components"))
    return await page.evaluate(() => document.querySelectorAll("*").length)
  } finally {
    await context.close()
  }
}

test("shoot() hands over the page drawn, also when its requests start after the network was quiet a while", async () => {
  assert.equal(await overviewElements(HELD_BACK_MS), await overviewElements(0))
})
