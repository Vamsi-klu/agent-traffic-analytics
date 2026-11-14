// The home page (S5.2, D37, D40) in Chromium, against the built app and the sample /api/setup and /api/settings: while
// nothing is recorded it is the onboarding (the website's address, where AgentCake runs, the page script with the
// sentence for a coding agent in English or Chinese, the first visit; example data beside it); a saved address shows in
// the top bar; the first visit shows up and opens the dashboard; from the first recorded session on it is the
// dashboard, as cake 0.3.4's page was. Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { openTab, sample, startApp } from "./app.mjs"

const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const setup = sample("setup"), settings = sample("settings")

async function open(answer) {
  const tab = await openTab(app)
  if (answer) await tab.page.route("**/api/setup", (route) => route.fulfill({ json: answer }))
  await tab.page.goto(app.url("#/"))
  return tab
}

test("with nothing recorded, / is the onboarding: four steps, the sentence in English or Chinese, example data", async () => {
  assert.deepEqual(setup.recorded, { sessions: 0, agent: 0 })
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    const steps = await tab.page.getByRole("heading", { level: 2 }).allInnerTexts()
    assert.deepEqual(steps.map((t) => t.replace(/^\d+\s*/, "")), ["Your website's address", "Where AgentCake runs", "Add the script to your pages", "Wait for the first visit"])
    await tab.page.getByRole("heading", { name: "Copy to your coding agent" }).waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.locator("pre").filter({ hasText: setup.sentence.en }).count(), 1)
    await tab.page.getByRole("radio", { name: "中文" }).click()
    assert.equal(await tab.page.locator("pre").filter({ hasText: setup.sentence.zh }).count(), 1)
    assert.deepEqual(await tab.page.getByRole("tab").allInnerTexts(), ["On this computer", "On a server", "Script tag", "Terminal"])
    assert.ok(await tab.page.getByText("No visits yet").isVisible())
    assert.ok(await tab.page.getByText("Example data", { exact: true }).isVisible())
    assert.equal(await tab.page.getByText(/demo shop/i).count(), 0, "D37: no demo shop")
    assert.equal(await tab.page.getByRole("link", { name: "Skip for now" }).count(), 0)
    assert.match(tab.page.url(), /#\/$/)
  } finally { await tab.close() }
})

test("in server mode step 2 says AgentCake runs on this server", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "server" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByText("AgentCake runs on this server.", { exact: false }).waitFor({ timeout: WAIT_MS })
    assert.deepEqual(await tab.page.getByRole("tab").allInnerTexts(), ["Script tag", "Terminal"])
  } finally { await tab.close() }
})

test("a saved address shows in the top bar, opening the site in a new tab (D40)", async () => {
  const tab = await open()
  try {
    await tab.page.route("**/api/settings", (route) => route.request().method() === "POST"
      ? route.fulfill({ json: { ...settings, site_domain: "shop.example.org" } }) : route.fulfill({ json: { ...settings, site_domain: "" } }))
    await tab.page.reload()
    const none = tab.page.getByRole("link", { name: "Set up your website" })
    await none.waitFor({ timeout: WAIT_MS })
    await tab.page.getByLabel("Your website's domain").fill("shop.example.org")
    await tab.page.getByRole("button", { name: "Save" }).click()
    const project = tab.page.getByRole("link", { name: /shop\.example\.org/ })
    await project.waitFor({ timeout: WAIT_MS })
    assert.equal(await project.getAttribute("href"), "https://shop.example.org/")
    assert.equal(await project.getAttribute("target"), "_blank")
  } finally { await tab.close() }
})

test("the first visit shows up within refresh_ms and opens the dashboard", async () => {
  const tab = await openTab(app)
  try {
    const list = sample("sessions")
    let asked = 0
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, refresh_ms: 200 } }))
    await tab.page.route("**/api/sessions**", (route) => route.fulfill({ json: asked++ ? list : { ...list, results: [] } }))
    await tab.page.route("**/api/setup", (route) => route.fulfill({ json: asked > 1 ? { ...setup, recorded: { sessions: 1, agent: 0 } } : setup }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByText("First visit received").waitFor({ timeout: WAIT_MS })
    await tab.page.getByRole("button", { name: "Open dashboard" }).click()
    await tab.page.waitForURL(/#\/dashboard$/, { timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("from the first recorded session on, / is the dashboard", async () => {
  const tab = await open({ ...setup, recorded: { sessions: 1, agent: 0 } })
  try {
    await tab.page.waitForURL(/#\/dashboard$/, { timeout: WAIT_MS })
    await tab.page.getByRole("heading", { name: "Dashboard", level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.getByRole("heading", { name: "Copy to your coding agent" }).count(), 0)
  } finally { await tab.close() }
})
