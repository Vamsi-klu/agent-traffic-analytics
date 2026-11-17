// Drives Chromium for tests/browser/test_identify.py: window.cake.identify() and window.cake.reset() against the
// stand-in collector (tests/browser/collector.py), each scenario in a browser context of its own (a profile).
//   node tests/browser/identify.mjs --base http://127.0.0.1:<port> --out <dir> --id <the site's id for the visitor>
// Writes <out>/<scenario>.json with what the page kept (localStorage's visitor entry, the session id) at each step,
// and <out>/requests.ndjson with every request the pages made (address, headers, body as text), for the test to look
// for the id in. The id is never put in a page address: every upload carries the page's address.
//   signin     identify() on a page, then a second page, then reset(), then stop()
//   other      another profile signs in with the same id
//   queued     window.cake.push(['identify', id]) before cake.js has loaded
//   consent    data-consent="required": identify() before Accept stores and sends nothing; after Accept it does
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { appendFile, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { executablePath } from './chromium.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))
const CAKEJS = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const STORAGE = CAKEJS.storage

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const base = args.base
const SEND_MS = CAKEJS.batch.interval_min_ms + 1500 // a timer batch has gone, and its answer arrived
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function launch() {
  return chromium.launch({ executablePath: executablePath() })
}

/** A new profile whose every request is written to requests.ndjson. */
async function profile(browser) {
  const context = await browser.newContext()
  context.on('request', (request) => {
    const line = { url: request.url(), headers: request.headers(), body: request.postData() }
    appendFile(path.join(args.out, 'requests.ndjson'), JSON.stringify(line) + '\n')
  })
  return context
}

/** What the page keeps: the visitor entry (id, last use, identify hash) and the session id. */
function kept(page) {
  return page.evaluate((keys) => ({
    visitor: JSON.parse(localStorage.getItem(keys.visitor) || 'null'), session: sessionStorage.getItem(keys.session)
  }), STORAGE)
}

/** A click on the page's heading: activity, so the page is not idle. */
async function poke(page) {
  await page.click('#title')
  await sleep(200)
}

async function signin(browser) {
  const context = await profile(browser)
  const page = await context.newPage()
  const log = {}
  await page.goto(`${base}/pages/plain.html`)
  await sleep(SEND_MS)
  log.before = await kept(page)
  await page.evaluate((id) => window.cake.identify(id), args.id)
  await poke(page)
  await sleep(SEND_MS)
  log.signedIn = await kept(page)
  await page.goto(`${base}/pages/plain.html?page=2`)
  await sleep(SEND_MS)
  log.secondPage = await kept(page)
  await page.evaluate(() => window.cake.reset())
  await poke(page)
  await sleep(SEND_MS)
  log.afterReset = await kept(page)
  await page.evaluate(() => window.cake.stop())
  log.afterStop = await kept(page)
  await context.close()
  return log
}

async function other(browser) {
  const context = await profile(browser)
  const page = await context.newPage()
  await page.goto(`${base}/pages/plain.html`)
  await page.evaluate((id) => window.cake.identify(id), args.id)
  await poke(page)
  await sleep(SEND_MS)
  const log = { signedIn: await kept(page) }
  await context.close()
  return log
}

async function queued(browser) {
  const context = await profile(browser)
  const page = await context.newPage()
  await page.addInitScript((id) => {
    window.cake = window.cake || []
    window.cake.push(['identify', id])
  }, args.id)
  await page.goto(`${base}/pages/plain.html`)
  await sleep(SEND_MS)
  const log = { signedIn: await kept(page) }
  await context.close()
  return log
}

async function consent(browser) {
  const context = await profile(browser)
  const page = await context.newPage()
  await page.goto(`${base}/pages/consent.html`)
  await sleep(500)
  await page.evaluate((id) => window.cake.identify(id), args.id)
  await sleep(SEND_MS)
  const log = { beforeAccept: await kept(page) }
  await page.click('#accept')
  await sleep(SEND_MS)
  log.afterAccept = await kept(page)
  await context.close()
  return log
}

await mkdir(args.out, { recursive: true })
const browser = await launch()
try {
  for (const [name, scenario] of Object.entries({ signin, other, queued, consent })) {
    await writeFile(path.join(args.out, `${name}.json`), JSON.stringify(await scenario(browser), null, 2))
  }
} finally {
  await browser.close()
}
