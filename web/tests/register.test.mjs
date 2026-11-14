// The registration card in Chromium, against the built app with /api/register answered here: until this
// AgentCake has registered, every page shows the card first, in the user's own words; the button stays off until the
// email address passes cake's check; "See what's sent" shows the exact text the button posts, once; a registration
// that can't be sent says why, lets the owner in with Continue, is not tried again, and the card asks again the next
// time the dashboard opens. Usage: node --test tests/
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { after, before, test } from "node:test"
import { openTab, sample, startApp } from "./app.mjs"

const WAIT_MS = 15000
const NAME = JSON.parse(readFileSync(new URL("../../agentcake/data/product.json", import.meta.url), "utf8")).name
/** The card's words the user wrote, which stay exactly as they are. */
const USERS_WORDS = [
  `Welcome to ${NAME}`,
  "Free, open-source agent analytics",
  `${NAME} is an open-source project. We're looking for early users to help shape what we build next.`,
  "Register your installation to get started. Your website analytics and session recordings stay on your own server.",
  "Your registration details will be sent to Tartini AI. No website traffic, session replay or product usage telemetry is sent.",
]
const firstRun = sample("register/first-run"), registered = sample("register")
const NOT_SENT = "Couldn't reach tartini.ai: no internet connection. Your registration wasn't sent. Check your internet connection, then try again."

let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** A tab whose /api/register answers as an AgentCake that hasn't registered; posts are noted and answered by `post`. */
async function openUnregistered({ post = () => ({ status: 200, json: registered }), width } = {}) {
  const tab = await openTab(app, { width })
  const posts = []
  await tab.page.route("**/api/register", (route) => {
    const request = route.request()
    if (request.method() !== "POST") return route.fulfill({ json: firstRun })
    posts.push({ body: request.postData(), type: request.headers()["content-type"] })
    return route.fulfill(post())
  })
  return { ...tab, posts }
}

const card = (page) => page.getByRole("form", { name: `Welcome to ${NAME}` })

test("until it has registered, every page shows the card first, in the user's words", async () => {
  const tab = await openUnregistered()
  try {
    for (const route of ["#/", "#/dashboard", "#/sessions", "#/settings"]) {
      await tab.page.goto(app.url(route))
      await tab.page.getByRole("heading", { name: `Welcome to ${NAME}`, level: 1 }).waitFor({ timeout: WAIT_MS })
      const text = await tab.page.locator("main").innerText()
      for (const words of USERS_WORDS) assert.ok(text.includes(words), `${route}: "${words}"`)
      assert.equal(await tab.page.getByRole("heading", { name: "Dashboard", level: 1 }).count(), 0, route)
    }
    assert.ok(await tab.page.getByLabel("Email address").isVisible())
    assert.ok(await tab.page.getByLabel("Company (optional)").isVisible())
    assert.equal(await tab.page.getByRole("checkbox").isChecked(), false, "product updates: not ticked")
    assert.equal(tab.posts.length, 0, "nothing is posted until the button is pressed")
  } finally { await tab.close() }
})

test("the button stays off until the email address passes cake's check", async () => {
  const tab = await openUnregistered()
  try {
    await tab.page.goto(app.url("#/"))
    const button = tab.page.getByRole("button", { name: "Register & Continue" })
    await button.waitFor({ timeout: WAIT_MS })
    const email = tab.page.getByLabel("Email address")
    for (const typed of ["", "owner", "owner@", "owner@example", "owner @example.com"]) {
      await email.fill(typed)
      assert.equal(await button.isDisabled(), true, `"${typed}"`)
    }
    await email.fill(" owner@example.com ")
    assert.equal(await button.isDisabled(), false)
  } finally { await tab.close() }
})

test("See what's sent shows the very text the button posts, once, and then the pages open", async () => {
  const tab = await openUnregistered()
  try {
    await tab.page.goto(app.url("#/"))
    await tab.page.getByLabel("Email address").fill("owner@example.com")
    await tab.page.getByLabel("Company (optional)").fill("Bäckerei Ünal")
    await tab.page.getByRole("checkbox").check()
    await tab.page.getByRole("button", { name: "See what's sent" }).click()
    const shown = await tab.page.getByLabel("What's sent").locator("pre").innerText()
    assert.deepEqual(JSON.parse(shown), { email: "owner@example.com", company: "Bäckerei Ünal", product_updates: true, consent_version: firstRunVersion(shown) })
    await tab.page.getByRole("button", { name: "Register & Continue" }).click()
    await tab.page.getByRole("heading", { name: "Copy to your coding agent" }).waitFor({ timeout: WAIT_MS })
    assert.deepEqual(tab.posts, [{ body: shown, type: "application/json" }])
  } finally { await tab.close() }
})

test("a registration that can't be sent says why, lets the owner in, isn't tried again, and the card asks next time", async () => {
  const tab = await openUnregistered({ post: () => ({ status: 502, json: { error: NOT_SENT } }) })
  try {
    await tab.page.goto(app.url("#/dashboard"))
    await tab.page.getByLabel("Email address").fill("owner@example.com")
    await tab.page.getByRole("button", { name: "Register & Continue" }).click()
    const alert = card(tab.page).getByRole("alert")
    await alert.waitFor({ timeout: WAIT_MS })
    assert.match(await alert.innerText(), new RegExp(NOT_SENT.replace(/[()]/g, "\\$&")))
    assert.equal(await tab.page.getByRole("button", { name: "Register & Continue" }).count(), 0, "no second try offered")
    await tab.page.getByRole("button", { name: "Continue" }).click()
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS })
    await tab.page.goto(app.url("#/sessions"))
    await tab.page.getByRole("heading", { name: "Sessions", level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.equal(tab.posts.length, 1, "sent once, never again")
    await tab.page.reload()
    await tab.page.getByRole("heading", { name: `Welcome to ${NAME}`, level: 1 }).waitFor({ timeout: WAIT_MS })
    assert.equal(tab.posts.length, 1)
  } finally { await tab.close() }
})

test("what cake refuses for what was typed keeps the form and says why", async () => {
  const tab = await openUnregistered({ post: () => ({ status: 400, json: { error: "Enter a company name of up to 200 characters, on one line." } }) })
  try {
    await tab.page.goto(app.url("#/"))
    await tab.page.getByLabel("Email address").fill("owner@example.com")
    await tab.page.getByRole("button", { name: "Register & Continue" }).click()
    await card(tab.page).getByRole("alert").waitFor({ timeout: WAIT_MS })
    assert.equal(await tab.page.getByRole("button", { name: "Register & Continue" }).isDisabled(), false, "it can be pressed again")
  } finally { await tab.close() }
})

test("a registered AgentCake opens the pages at once", async () => {
  const tab = await openTab(app) // the samples' /api/register: registered
  try {
    await tab.page.goto(app.url("#/dashboard"))
    await tab.page.getByRole("heading", { name: "Connect your website", level: 1 }).waitFor({ timeout: WAIT_MS }) // nothing recorded in the samples
    assert.equal(await tab.page.getByRole("heading", { name: `Welcome to ${NAME}` }).count(), 0)
  } finally { await tab.close() }
})

/** The consent version the page wrote (its own words' date), checked for its form only: the page owns it. */
function firstRunVersion(shown) {
  const version = JSON.parse(shown).consent_version
  assert.match(version, /^\d{4}-\d{2}-\d{2}$/)
  return version
}
