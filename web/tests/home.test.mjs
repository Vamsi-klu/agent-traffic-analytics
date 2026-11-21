// The home page in Chromium, against the built app and the sample /api/setup and /api/settings: until the website has
// sent a session it is the onboarding (the website's address, where AgentCake runs, the page script with the sentence
// for a coding agent in English or Chinese, the first visit; sample data beside it), however many sessions an earlier
// AgentCake's demo shop recorded; a saved address shows in the top bar, and until then "Set up your website" opens the
// four steps while the website isn't connected and Settings once it is; the website's first visit shows up (a demo shop
// session doesn't count) and opens the dashboard; from the website's first session on it is the dashboard, as cake
// 0.3.4's page was. Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { openTab, sample, startApp } from "./app.mjs"

const WAIT_MS = 15000
let app
before(async () => { app = await startApp() })
after(() => app?.close())

const setup = sample("setup"), settings = sample("settings")
/** A demo shop session in the list: the sample list's first row, marked as an earlier AgentCake's demo shop recorded it. */
const demoRow = (list) => ({ ...list.results[0], id: "demo-1", demo_shop: true })

async function open(answer) {
  const tab = await openTab(app)
  if (answer) await tab.page.route("**/api/setup", (route) => route.fulfill({ json: answer }))
  await tab.page.goto(app.url("#/"))
  return tab
}

/** Opens "Install manually", where the steps are. */
async function manual(page) {
  const toggle = page.getByRole("button", { name: "Install manually" })
  await toggle.click()
  assert.equal(await toggle.getAttribute("aria-expanded"), "true")
}

test("with nothing recorded, / is the onboarding: the sentence for an AI agent first, then Install manually, the first visit under both", async () => {
  assert.deepEqual(setup.recorded, { sessions: 0, site: 0, agent: 0 })
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    const headings = async () => (await tab.page.getByRole("heading", { level: 2 }).allInnerTexts()).map((t) => t.replace(/^\d+\s*/, ""))
    assert.deepEqual(await headings(), ["Install with your AI agent", "Wait for the first visit"])
    assert.equal(await tab.page.locator("pre").filter({ hasText: setup.sentence }).count(), 1)
    assert.match(setup.sentence, /^Connect this website to AgentCake\. To get started, download the guide at https:\/\/raw\.githubusercontent\.com\/\S+\/v[\d.]+\/INSTALL\.md with curl or the GitHub CLI\. .*its command is `agentcake`/)
    assert.ok(setup.sentence.includes("If the download fails, ask for network access."), "an agent without network asks for it, as README's sentence says")
    assert.ok(await tab.page.getByText("Review its plan, including where AgentCake runs and any costs, and approve it.", { exact: false }).isVisible(), "the owner approves the agent's plan before it connects the website")
    assert.equal(await tab.page.getByRole("radio").count(), 0, "the sentence is in English only: no language to pick")
    assert.equal(await tab.page.getByRole("tab").count(), 0, "the steps wait behind Install manually")
    assert.ok(await tab.page.getByText("No visits yet").isVisible())
    await manual(tab.page)
    assert.deepEqual(await headings(), ["Install with your AI agent", "Enter your website's address", "Choose where AgentCake runs", "Add the script to your pages", "Wait for the first visit"])
    assert.deepEqual(await tab.page.getByRole("tab").allInnerTexts(), ["On a server", "On this computer", "Script tag", "Terminal"])
    assert.equal(await tab.page.getByRole("tab", { name: "On a server" }).getAttribute("aria-selected"), "true", "a server by default")
    assert.ok(await tab.page.getByText("Paste this line once, before the closing </head> tag in the layout or template that every page uses", { exact: false }).isVisible())
    assert.ok(await tab.page.getByText("Sample data", { exact: true }).isVisible())
    assert.equal(await tab.page.getByText(/demo shop/i).count(), 0, "no demo shop")
    assert.equal(await tab.page.getByRole("link", { name: "Skip for now" }).count(), 0)
    assert.match(tab.page.url(), /#\/$/)
  } finally { await tab.close() }
})

test("the note under the prompt says who does what: with approval the agent creates a server and adds a DNS record, the owner signs in", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Install with your AI agent", level: 2 }).waitFor({ timeout: WAIT_MS })
    const note = await tab.page.locator("pre").filter({ hasText: setup.sentence }).locator("xpath=following::p[1]").innerText()
    for (const fact of [/\bapprov/i, /\bcreates? a server\b/i, /\badds? a DNS record\b/i, /\bsign in\b/i]) assert.match(note, fact)
    assert.doesNotMatch(note, /guides you through/i)
  } finally { await tab.close() }
})

test("the heading has no description under it: only the status tag above it, which says where AgentCake runs", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    const heading = tab.page.getByRole("heading", { name: "Connect your website", level: 1 })
    await heading.waitFor({ timeout: WAIT_MS })
    const header = heading.locator("xpath=..")
    assert.equal(await header.locator("p").count(), 0)
    assert.equal((await header.innerText()).replace(/\s+/g, " ").trim(), "AgentCake is running on this computer Connect your website")
  } finally { await tab.close() }
})

test("in server mode step 2 says AgentCake runs on this server", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "server" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.ok(await tab.page.getByText("AgentCake is running on this server", { exact: true }).isVisible(), "the status tag says so too")
    await manual(tab.page)
    await tab.page.getByText("AgentCake is running on this server.", { exact: false }).waitFor({ timeout: WAIT_MS })
    assert.deepEqual(await tab.page.getByRole("tab").allInnerTexts(), ["Script tag", "Terminal"])
  } finally { await tab.close() }
})

test("on this computer, step 2's server tab says in the owner's words why a public website needs a server", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    await manual(tab.page)
    const server = tab.page.getByRole("tabpanel", { name: "On a server" })
    assert.equal(await server.locator("p").first().innerText(), "You can't collect data from visitors to your public website if AgentCake is only accessible on your computer. "
      + "To collect their visit data, run AgentCake on a server that can receive data from their browsers, then connect your website to it.")
  } finally { await tab.close() }
})

test("on this computer, step 2's server tab names the three things a public website takes: a server, a DNS record and its settings", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, route: "this_computer" } }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    await manual(tab.page)
    const server = tab.page.getByRole("tabpanel", { name: "On a server" })
    assert.deepEqual(await server.getByRole("heading", { level: 3 }).allInnerTexts(), ["A server", "A DNS record", "Settings on the server"])
    for (const part of ["install", "dns", "settings"]) {
      assert.equal(await server.locator("pre").filter({ hasText: setup.server[part] }).count(), 1, part)
    }
    assert.match(setup.server.install, /docker compose up -d/)
    assert.match(setup.server.settings, /config set public_url https:\/\/cake\./)
    const words = await server.innerText()
    assert.match(words, /Add this record in your DNS provider's settings to point your subdomain to your server/)
    assert.match(words, /On Cloudflare, set the record to DNS only \(gray cloud\)/)
    assert.match(words, /Caddy automatically obtains and renews the HTTPS certificate/)
    assert.equal(await server.getByRole("link", { name: "SERVER.md" }).count(), 1, "the full steps, or systemd")
  } finally { await tab.close() }
})

test("a saved address shows in the top bar, opening the site in a new tab", async () => {
  const tab = await open()
  try {
    await tab.page.route("**/api/settings", (route) => route.request().method() === "POST"
      ? route.fulfill({ json: { ...settings, site_domain: "shop.example.org" } }) : route.fulfill({ json: { ...settings, site_domain: "" } }))
    await tab.page.reload()
    const none = tab.page.getByRole("link", { name: "Set up your website" })
    await none.waitFor({ timeout: WAIT_MS })
    await manual(tab.page)
    await tab.page.getByLabel("Website domain").fill("shop.example.org")
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
    await tab.page.route("**/api/setup", (route) => route.fulfill({ json: asked > 1 ? { ...setup, recorded: { sessions: 1, site: 1, agent: 0 } } : setup }))
    await tab.page.goto(app.url("#/"))
    await tab.page.getByText("First visit received").waitFor({ timeout: WAIT_MS })
    await tab.page.getByRole("button", { name: "Go to dashboard" }).click()
    await tab.page.waitForURL(/#\/dashboard$/, { timeout: WAIT_MS })
  } finally { await tab.close() }
})

test("with only the demo shop's sessions, / stays the four steps, and step 4 waits for the website's own first visit", async () => {
  const tab = await openTab(app)
  try {
    const list = sample("sessions")
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, site_domain: "", refresh_ms: 200 } }))
    await tab.page.route("**/api/setup", (route) => route.fulfill({ json: { ...setup, recorded: { sessions: 1, site: 0, agent: 0 } } }))
    await tab.page.route("**/api/sessions**", (route) => route.fulfill({ json: { ...list, results: [demoRow(list)], total: 1 } }))
    const askedForSessions = () => tab.page.waitForResponse((r) => new URL(r.url()).pathname === "/api/sessions", { timeout: WAIT_MS })
    await tab.page.goto(app.url("#/"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    for (const _ of [1, 2, 3]) await askedForSessions() // step 4 asks again every refresh_ms; each answer is the demo shop's
    assert.ok(await tab.page.getByText("No visits yet").isVisible(), "a demo shop session isn't the website's first visit")
    assert.equal(await tab.page.getByText("First visit received").count(), 0)
    assert.match(tab.page.url(), /#\/$/)
    assert.equal(await tab.page.getByRole("link", { name: "Set up your website" }).getAttribute("href"), "#/", "the top bar opens the four steps")
  } finally { await tab.close() }
})

test("once the website has sent a session, the top bar's Set up your website opens Settings", async () => {
  const tab = await openTab(app)
  try {
    await tab.page.route("**/api/settings", (route) => route.fulfill({ json: { ...settings, site_domain: "" } }))
    await tab.page.route("**/api/setup", (route) => route.fulfill({ json: { ...setup, recorded: { sessions: 2, site: 1, agent: 0 } } }))
    await tab.page.goto(app.url("#/settings"))
    const link = tab.page.getByRole("link", { name: "Set up your website" })
    await link.waitFor({ timeout: WAIT_MS })
    await tab.page.waitForFunction(() => document.querySelector('a[href="#/settings"]')?.textContent?.includes("Set up your website"), undefined, { timeout: WAIT_MS })
    assert.equal(await link.getAttribute("href"), "#/settings")
  } finally { await tab.close() }
})

test("from the website's first session on, / is the dashboard", async () => {
  const tab = await open({ ...setup, recorded: { sessions: 1, site: 1, agent: 0 } })
  try {
    await tab.page.waitForURL(/#\/dashboard$/, { timeout: WAIT_MS })
    await tab.page.getByRole("heading", { name: "Dashboard", level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.getByRole("heading", { name: "Install with your AI agent" }).count(), 0)
  } finally { await tab.close() }
})

test("on the way to the dashboard / keeps the address's query: #/?range=30d opens #/dashboard?range=30d", async () => {
  const tab = await openTab(app)
  try {
    const ranges = []
    tab.page.on("request", (request) => { if (request.url().includes("/api/overview")) ranges.push(new URL(request.url()).searchParams.get("range")) })
    await tab.page.route("**/api/setup", (route) => route.fulfill({ json: { ...setup, recorded: { sessions: 1, site: 1, agent: 0 } } }))
    await tab.page.goto(app.url("#/?range=30d"))
    await tab.page.waitForURL(/#\/dashboard\?range=30d$/, { timeout: WAIT_MS })
    await tab.page.getByRole("combobox", { name: "Date range" }).filter({ hasText: "Last 30 days" }).waitFor({ timeout: WAIT_MS })
    assert.deepEqual([...new Set(ranges)], ["30d"], "the dashboard asks for the last 30 days, never the default range")
  } finally { await tab.close() }
})
