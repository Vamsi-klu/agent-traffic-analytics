// The top bar's Style menu (DESIGN.md §17), in Chromium against the built app: a browser that picked nothing opens in
// Cake; the menu lists Cake and Minimal, each with its preview, the one in use checked; choosing one changes the page at
// once, without loading it again, and the next visit opens in it; a browser that keeps no site data, or keeps something
// else under the style's key, opens in Cake, and the menu still changes the page. Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { startApp } from "./app.mjs"
import { shoot } from "../scripts/shots.mjs"

const ROUTE = "#/dashboard"
let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** A page of a fresh browser at 1280 wide; `setup` runs in every document before the app (an init script). */
async function open(setup) {
  const context = await app.browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light", reducedMotion: "reduce" })
  if (setup) await context.addInitScript(setup)
  const page = await context.newPage()
  await shoot(page, app.url(ROUTE))
  return { page, context }
}

/** The style the page shows: the root's data-style, none for Cake. */
const shown = (page) => page.evaluate(() => document.documentElement.dataset.style ?? "cake")
const button = (page) => page.getByRole("button", { name: /^Style: / })

async function choose(page, name) {
  await button(page).click()
  await page.getByRole("menuitemradio", { name }).click()
}

test("a browser that picked no style opens in Cake, and the button names it", async () => {
  const { page, context } = await open()
  try {
    assert.equal(await shown(page), "cake")
    assert.equal(await button(page).getAttribute("aria-label"), "Style: Cake")
  } finally {
    await context.close()
  }
})

test("the menu lists Cake and Minimal, each with its preview, and checks the style in use", async () => {
  const { page, context } = await open()
  try {
    await button(page).click()
    const items = page.getByRole("menuitemradio")
    assert.deepEqual(await items.allTextContents(), ["Cake", "Minimal"])
    assert.deepEqual(await items.evaluateAll((all) => all.map((item) => item.getAttribute("aria-checked"))), ["true", "false"])
    const previews = await items.locator("img").evaluateAll((all) => all.map((img) => [img.complete, img.naturalWidth, img.naturalHeight]))
    assert.deepEqual(previews, [[true, 480, 300], [true, 480, 300]], "each item shows its 480 x 300 preview")
  } finally {
    await context.close()
  }
})

test("choosing Minimal changes the page at once, the next visit opens in it, and choosing Cake goes back", async () => {
  const { page, context } = await open()
  try {
    await page.evaluate(() => { window.notReloaded = true })
    await choose(page, "Minimal")
    assert.equal(await shown(page), "minimal")
    assert.equal(await page.evaluate(() => window.notReloaded), true, "the page was not loaded again")
    assert.equal(await button(page).getAttribute("aria-label"), "Style: Minimal")
    await page.reload({ waitUntil: "networkidle" }) // the next visit
    assert.equal(await shown(page), "minimal")
    await choose(page, "Cake")
    await page.reload({ waitUntil: "networkidle" })
    assert.equal(await shown(page), "cake")
  } finally {
    await context.close()
  }
})

test("a browser that keeps no site data opens in Cake, and the menu still changes the page", async () => {
  const { page, context } = await open(() => {
    Object.defineProperty(window, "localStorage", { get() { throw new DOMException("site data is turned off", "SecurityError") } })
  })
  try {
    assert.equal(await shown(page), "cake")
    await choose(page, "Minimal")
    assert.equal(await shown(page), "minimal")
  } finally {
    await context.close()
  }
})

test("a browser that keeps something else under the style's key opens in Cake", async () => {
  const { page, context } = await open(() => {
    if (location.protocol.startsWith("http")) localStorage.setItem("agentcake-style", "dark")
  })
  try {
    assert.equal(await shown(page), "cake")
  } finally {
    await context.close()
  }
})
