// browser-check.mjs — the token in a real browser: Chromium through Playwright, headless and with a window, on the test
// site (test-site.js) with a fresh random secret. Each run opens the home page, follows the link to the second page,
// follows the link back (a 304: the pages are no-cache with an ETag) and reloads. For every page request it compares the
// four Sec-Fetch values inside the token with the request headers Chrome sent, as Chrome's DevTools protocol records
// them (Network.requestWillBeSentExtraInfo), checks the token verifies, and notes which token the page itself sees in
// its navigation entry (what cake.js reads): this response's, an earlier one's, or none (case T8, middleware).
//
//   node edge/node/scripts/browser-check.mjs [--out <folder>] [--modes headless,headed] [--no-store]
//
// Playwright comes from web/node_modules (CAKE_PLAYWRIGHT: another playwright-core folder); the browser is Playwright's
// Chromium, found as web/scripts/shots.mjs finds it (CAKE_CHROME: another executable). Exit status 1 on any mismatch.
import crypto from "node:crypto"
import { existsSync, mkdirSync, writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.join(here, "..", "..", "..")
const require = createRequire(import.meta.url)
const { startSite } = require("./test-site.js")
const { verifyToken } = require("../index.js")
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, "web", "node_modules", "playwright-core"))

const SEC_FETCH = { s: "sec-fetch-site", m: "sec-fetch-mode", d: "sec-fetch-dest", u: "sec-fetch-user" }
const SECRET_BYTES = 32

function argument(name, fallback) {
  const at = process.argv.indexOf(name)
  return at === -1 ? fallback : process.argv[at + 1]
}

function launch(headless) {
  const guess = path.join(process.env.HOME, "Library/Caches/ms-playwright/chromium-1228/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
  const executablePath = process.env.CAKE_CHROME || (existsSync(guess) ? guess : undefined)
  return chromium.launch({ executablePath, headless })
}

const lower = (headers) => Object.fromEntries(Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), value]))
const tokenIn = (serverTiming) => (/(?:^|,)\s*cake;desc="([^"]+)"/.exec(serverTiming || "") || [])[1] || null

// Every main-frame document request the page makes, with the headers Chrome sent and the response's head.
function recordDocuments(cdp) {
  const byId = new Map()
  const order = []
  const entry = (id) => {
    if (!byId.has(id)) byId.set(id, {})
    return byId.get(id)
  }
  cdp.on("Network.requestWillBeSent", (event) => {
    if (event.type !== "Document") return
    Object.assign(entry(event.requestId), { url: event.request.url, method: event.request.method })
    order.push(event.requestId)
  })
  cdp.on("Network.requestWillBeSentExtraInfo", (event) => { entry(event.requestId).sent = lower(event.headers) })
  cdp.on("Network.responseReceivedExtraInfo", (event) => Object.assign(entry(event.requestId), { status: event.statusCode, received: lower(event.headers) }))
  return () => order.map((id) => byId.get(id))
}

async function seenByPage(page) {
  return page.evaluate(() => {
    const entry = performance.getEntriesByType("navigation")[0]
    const cake = entry.serverTiming.find((each) => each.name === "cake")
    return { type: entry.type, responseStatus: entry.responseStatus ?? null, token: cake ? cake.description : null }
  })
}

async function runMode(mode, site, secret, out) {
  const browser = await launch(mode === "headless")
  const steps = []
  try {
    const context = await browser.newContext()
    const page = await context.newPage()
    const cdp = await context.newCDPSession(page)
    await cdp.send("Network.enable")
    const documents = recordDocuments(cdp)
    const visits = [
      ["open the home page", () => page.goto(site.url)],
      ["follow the link to the second page", async () => { await page.click("#link"); await page.waitForURL(`${site.url}next`) }],
      ["follow the link back home (304 unless noStore)", async () => { await page.click("#link"); await page.waitForURL(site.url) }],
      ["reload", () => page.reload()],
    ]
    const tokensSoFar = []
    for (const [n, [step, go]] of visits.entries()) {
      const before = documents().length
      await go()
      await page.waitForLoadState("load")
      const request = documents().slice(before).pop()
      const response = tokenIn(request && request.received && request.received["server-timing"])
      const pageSees = await seenByPage(page)
      const verified = response ? await verifyToken(secret, response) : { result: "no token" }
      const sentValues = Object.fromEntries(Object.entries(SEC_FETCH).map(([key, name]) => [key, request && request.sent && name in request.sent ? request.sent[name] : null]))
      const tokenValues = verified.payload ? verified.payload.sf : null
      const seen = pageSees.token === null ? "none" : pageSees.token === response ? "this response's" : tokensSoFar.includes(pageSees.token) ? "an earlier response's" : "unknown"
      steps.push({
        step,
        path: request ? new URL(request.url).pathname : null,
        status: request ? request.status : null,
        token_id: verified.payload ? verified.payload.id : null,
        token_verifies: verified.result,
        sec_fetch_sent: sentValues,
        sec_fetch_in_token: tokenValues,
        same: JSON.stringify(sentValues) === JSON.stringify(tokenValues),
        page_navigation_type: pageSees.type,
        page_response_status: pageSees.responseStatus,
        token_the_page_sees: seen,
      })
      if (response) tokensSoFar.push(response)
      if (n < 2) await page.screenshot({ path: path.join(out, `browser-${site.label}-${mode}-${n + 1}.png`) })
    }
  } finally {
    await browser.close()
  }
  return steps
}

async function main() {
  const out = path.resolve(argument("--out", path.join(os.tmpdir(), "agentcake-evidence", new Date().toISOString().slice(0, 10), "browser-check")))
  const modes = argument("--modes", "headless,headed").split(",")
  const noStore = process.argv.includes("--no-store")
  mkdirSync(out, { recursive: true })
  const secret = crypto.randomBytes(SECRET_BYTES).toString("base64url") // a fresh test secret, never written down
  const site = await startSite({ secret, noStore })
  site.label = noStore ? "nostore" : "etag"
  let mismatches = 0
  const report = { browser: null, site: noStore ? "noStore on (no 304)" : "no-cache + ETag (revisits are 304)", runs: {} }
  try {
    for (const mode of modes) {
      report.runs[mode] = await runMode(mode, site, secret, out)
      for (const step of report.runs[mode]) {
        if (!step.same || step.token_verifies !== "ok") mismatches++
        console.log(`${mode.padEnd(8)} ${step.step.padEnd(48)} ${String(step.status).padEnd(4)} sent ${JSON.stringify(step.sec_fetch_sent)} token ${step.same ? "same" : "DIFFERENT"}; the page sees ${step.token_the_page_sees}`)
      }
    }
    const browser = await launch(true)
    report.browser = browser.version()
    await browser.close()
  } finally {
    await site.close()
  }
  writeFileSync(path.join(out, `browser-${site.label}.json`), `${JSON.stringify(report, null, 2)}\n`)
  console.log(`${mismatches ? `${mismatches} mismatch(es)` : "every page request: the token's four Sec-Fetch values are the ones Chrome sent"} (${report.browser})`)
  process.exitCode = mismatches ? 1 : 0
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
