// The settings page (S5.5) in Chromium, against the built app with /api/settings answered here: every item shows what
// /api/settings and /api/register say; a change is posted at once with only its field, and a selector list the browser
// can't read isn't posted; where visits come from is asked again while the page is open (I3), leaving the form as it
// is; lists past I4 and a full budget warn; "Delete all data" asks first and then posts /api/delete for everything;
// the description of freeing space states the share of the budget it stops at as /api/settings gives it.
// Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { after, before, test } from "node:test"
import { openTab, sample, startApp } from "./app.mjs"

const WAIT_MS = 15000
const NAME = JSON.parse(readFileSync(new URL("../../agentcake/data/product.json", import.meta.url), "utf8")).name
const settings = sample("settings"), registered = sample("register")

let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** The settings page with /api/settings answered by `answer` (a POST merges its body in, as cake saves it) and every
 *  post noted; then() swaps the answer later on. */
async function open(answer = settings) {
  const tab = await openTab(app)
  const posts = [], deletes = []
  let current = answer
  await tab.page.route("**/api/settings", (route) => {
    const request = route.request()
    if (request.method() === "POST") {
      const body = JSON.parse(request.postData())
      posts.push(body)
      current = { ...current, ...body }
    }
    return route.fulfill({ json: current })
  })
  await tab.page.route("**/api/delete", (route) => {
    deletes.push(JSON.parse(route.request().postData()))
    current = { ...current, database: { ...current.database, sessions: 0 } }
    return route.fulfill({ json: { sessions: [] } })
  })
  await tab.page.goto(app.url("#/settings"))
  await tab.page.getByRole("heading", { name: "Settings", level: 1 }).waitFor({ timeout: WAIT_MS })
  await tab.page.getByText("Your website's domain").waitFor({ timeout: WAIT_MS })
  return { ...tab, posts, deletes, swap: (next) => { current = next } }
}

const text = (page) => page.locator("main").innerText()

test("every item shows what /api/settings and /api/register say", async () => {
  const tab = await open()
  try {
    const page = tab.page, shown = await text(page)
    assert.equal(await page.getByLabel("Your website's domain").inputValue(), settings.site_domain)
    assert.ok(shown.includes(settings.site_key))
    assert.ok((await page.locator("pre").allInnerTexts()).includes(settings.script_tag), "the line to add, with the key")
    for (const when of Object.values(settings.last_seen)) assert.ok(shown.includes(`Last: ${when}`), when)
    assert.ok(shown.includes("On a server"))
    assert.ok(shown.includes(`${settings.server_half.missing.join(", ")} didn't reach your site's server`))
    assert.ok(shown.includes(`A ${settings.server_half.logs.format} log was imported ${settings.server_half.logs.last}.`))
    assert.equal(await page.getByRole("radio", { name: "Keep everything" }).getAttribute("aria-checked"), "true")
    assert.equal(await page.getByRole("switch", { name: "Free space automatically" }).getAttribute("aria-checked"), "true")
    assert.equal(await page.getByRole("switch", { name: "Page lookup monitoring" }).getAttribute("aria-checked"), "false")
    assert.equal(await page.getByLabel("CSS masking selectors").inputValue(), settings.hide_selectors)
    assert.equal(await page.getByText("Runs locally", { exact: true }).count(), 4, "the four layers: shown, not switches")
    assert.ok(shown.includes(`The lists were built ${settings.lists.built}`) && shown.includes("Up to date"))
    assert.ok(shown.includes(`${NAME} doesn't collect usage data or telemetry.`))
    assert.equal(await page.getByLabel("What was sent").locator("pre").innerText(), registered.sent.body)
    assert.ok(shown.includes(`write to ${registered.delete_contact}`))
    assert.ok(!/Mask all page text|installed extensions|Export/.test(shown), "no switch or button without a feature behind it")
  } finally { await tab.close() }
})

test("a change is posted at once with only its field, and the page shows cake's answer", async () => {
  const tab = await open()
  try {
    const page = tab.page
    await page.getByRole("switch", { name: "Page lookup monitoring" }).click()
    await page.getByRole("radio", { name: "90 days" }).click()
    await page.getByText("Sessions older than 90 days are deleted every night").waitFor({ timeout: WAIT_MS })
    await page.getByLabel("Your website's domain").fill("shop.example.org")
    await page.getByRole("button", { name: "Save" }).first().click()
    await page.waitForFunction(() => document.querySelector("#site-domain + button")?.disabled === true)
    assert.deepEqual(tab.posts, [{ hook_dom: true }, { retention_days: 90 }, { site_domain: "shop.example.org" }])
    assert.equal(await page.getByRole("switch", { name: "Page lookup monitoring" }).getAttribute("aria-checked"), "true")
  } finally { await tab.close() }
})

test("a selector list the browser can't read isn't posted; one it reads is", async () => {
  const tab = await open()
  try {
    const page = tab.page, input = page.getByLabel("CSS masking selectors")
    const save = page.locator("#hide + button")
    await input.fill("#address {")
    assert.equal(await save.isDisabled(), true)
    assert.equal(await input.getAttribute("aria-invalid"), "true")
    await page.getByText("This browser can't read the entries as CSS selectors.").waitFor({ timeout: WAIT_MS })
    await input.fill(" .account-email, #address, .card-number ")
    await save.click()
    await page.waitForFunction(() => document.querySelector("#hide + button")?.disabled === true)
    assert.deepEqual(tab.posts, [{ hide_selectors: ".account-email, #address, .card-number" }])
  } finally { await tab.close() }
})

test("where visits come from is asked again while the page is open, and the form stays as it is (I3)", async () => {
  const waiting = { ...settings, refresh_ms: 200, sources: { ...settings.sources, site: "waiting" }, last_seen: { ...settings.last_seen, site: null } }
  const tab = await open(waiting)
  try {
    const page = tab.page
    await page.getByLabel("Your website's domain").fill("typed.example")
    tab.swap({ ...settings, site_domain: "other.example", last_seen: { ...settings.last_seen, site: "Today 10:00" } })
    await page.getByText("Last: Today 10:00").waitFor({ timeout: WAIT_MS })
    assert.equal(await page.getByLabel("Your website's domain").inputValue(), "typed.example", "what was being typed stays")
    assert.equal(tab.posts.length, 0)
  } finally { await tab.close() }
})

test("on this computer, the page says public visitors need AgentCake on a server", async () => {
  const tab = await open({ ...settings, route: "this_computer" })
  try {
    assert.ok((await text(tab.page)).includes("On this computer"))
    await tab.page.getByText("Visitors to a public website can't reach this computer.").waitFor({ timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("the description of freeing space states the share of the budget it stops at, as /api/settings gives it", async () => {
  const configured = settings.storage.free_to_pct, other = configured - 15
  for (const [shown, hidden] of [[configured, other], [other, configured]]) {
    const tab = await open({ ...settings, storage: { ...settings.storage, free_to_pct: shown } })
    try {
      const page = await text(tab.page)
      assert.match(page, new RegExp(`\\b${shown}% of the budget\\.`))
      assert.doesNotMatch(page, new RegExp(`\\b${hidden}% of the budget`))
    } finally { await tab.close() }
  }
})

test("lists past I4 warn and give the command; a full budget says new replays aren't stored", async () => {
  const late = { ...settings, lists: { ...settings.lists, age_days: 45, stale: true },
    storage: { ...settings.storage, used_bytes: settings.budget_mb * 1024 * 1024, replays_stopped: "budget" } }
  const tab = await open(late)
  try {
    const page = tab.page
    await page.getByText(`These lists are more than ${late.lists.max_age_days} days old.`).waitFor({ timeout: WAIT_MS })
    assert.ok((await page.locator("pre").allInnerTexts()).includes(late.lists.update_command))
    await page.getByText("The disk budget is full and nothing more can be freed").waitFor({ timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("Delete all data asks first, then posts /api/delete for every session", async () => {
  const tab = await open()
  try {
    const page = tab.page
    await page.getByRole("button", { name: "Delete all data" }).click()
    await page.getByRole("dialog", { name: "Delete all sessions" }).waitFor({ timeout: WAIT_MS })
    await page.getByRole("button", { name: "Cancel" }).click()
    await page.getByRole("dialog").waitFor({ state: "detached", timeout: WAIT_MS })
    assert.deepEqual(tab.deletes, [], "Cancel deletes nothing")
    await page.getByRole("button", { name: "Delete all data" }).click()
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click()
    await page.getByText(/· 0 sessions$/).waitFor({ timeout: WAIT_MS })
    assert.deepEqual(tab.deletes, [{ all: true }])
  } finally { await tab.close() }
})
