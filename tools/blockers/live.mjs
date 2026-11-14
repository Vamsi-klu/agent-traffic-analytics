// The browser half of tools/blockers/live.py: a real Chromium with uBO Lite, in a fresh temporary profile, opens the
// test site's pages and says what loaded. live.py starts AgentCake and the site and reads what AgentCake stored.
//
//   node live.mjs <job.json> <answer.json>
//
// job.json: {extension, profile, site_host, site_port, blank_page, canaries: [url], pages: [{name, url}], settle_ms,
// linger_ms, start_wait_s}. The site's host is mapped to 127.0.0.1:<site_port> (--host-resolver-rules), so a page is
// a page of that site, with AgentCake on its own path.
// answer.json: {filtering, pages: [{name, cake, failed: [{url, error}]}]}.
// Playwright comes from CAKE_PLAYWRIGHT (web/node_modules/playwright-core); Chromium from CAKE_CHROME, else
// Playwright's own Chromium build (channel "chromium": extensions do not run in the headless shell).
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))

const [jobFile, answerFile] = process.argv.slice(2)
const job = JSON.parse(readFileSync(jobFile, 'utf8'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const MS_PER_S = 1000
const POLL_MS = 1000

// Loads each canary as a script; true when one is blocked, i.e. the blocker filters.
async function filtering(context) {
  const page = await context.newPage()
  await page.goto(job.blank_page, { waitUntil: 'load' })
  const loaded = await page.evaluate((urls) => Promise.all(urls.map((url) => new Promise((resolve) => {
    const tag = document.createElement('script')
    tag.src = url
    tag.onload = () => resolve(true)
    tag.onerror = () => resolve(false)
    document.head.appendChild(tag)
  }))), job.canaries)
  await page.close()
  return loaded.includes(false)
}

async function visit(context, { name, url }) {
  const page = await context.newPage()
  const failed = []
  page.on('requestfailed', (r) => failed.push({ url: r.url(), error: r.failure()?.errorText }))
  await page.goto(url, { waitUntil: 'load' })
  await sleep(job.settle_ms)
  await page.mouse.move(200, 200)
  await page.mouse.move(260, 240, { steps: 8 })
  await sleep(job.linger_ms)
  const cake = await page.evaluate(() => typeof window.cake)
  await page.close({ runBeforeUnload: true })
  return { name, cake, failed }
}

const args = [`--host-resolver-rules=MAP ${job.site_host} 127.0.0.1:${job.site_port}`, '--no-first-run',
  `--disable-extensions-except=${job.extension}`, `--load-extension=${job.extension}`]
const options = process.env.CAKE_CHROME ? { executablePath: process.env.CAKE_CHROME } : { channel: 'chromium' }
const context = await chromium.launchPersistentContext(job.profile, { ...options, headless: true, args })
try {
  // the extension needs a moment after start before its rules apply
  let on = false
  for (const deadline = Date.now() + job.start_wait_s * MS_PER_S; !on && Date.now() < deadline; await sleep(POLL_MS)) {
    on = await filtering(context)
  }
  const pages = []
  for (const p of job.pages) pages.push(await visit(context, p))
  writeFileSync(answerFile, JSON.stringify({ filtering: on, pages }, null, 1))
} finally {
  await context.close()
}
