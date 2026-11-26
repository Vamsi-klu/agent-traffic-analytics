// Two browsers on the test site's shop (tests/site), its pages loading cake.js from a real AgentCake, for
// tests/browser/test_visit_tabs.py: in the first browser a visitor opens the shop, then another page of it in a second
// tab, and goes back and forth between them; in the second browser (another visitor) one tab. Every page is left
// before its browser closes, so that the uploads cake.js sends when a page is left reach AgentCake.
//
//   node tests/browser/visit_tabs.mjs --base http://127.0.0.1:<site port> --out <file>
//
// Writes <file>: {"first": [the pages of its tabs, in order], "second": [...]}. playwright-core comes from
// CAKE_PLAYWRIGHT or web/node_modules/playwright-core, Chromium as chromium.mjs picks it.
import { writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { executablePath } from './chromium.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const VIEWPORT = { width: 1280, height: 900 }
const ACT_MS = 1500 // what a visitor does on a page: enough for cake.js to send a batch
const SETTLE_MS = 2000 // after the pages are left: let their last uploads land before the browser closes

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function act(page) {
  await page.bringToFront()
  for (let step = 0; step < 10; step++) {
    await page.mouse.move(100 + step * 40, 200 + step * 10)
  }
  await page.mouse.wheel(0, 300)
  await sleep(ACT_MS)
}

async function visit(browser, paths) {
  const context = await browser.newContext({ viewport: VIEWPORT })
  const tabs = []
  for (const where of paths) {
    const page = await context.newPage()
    await page.goto(args.base + where, { waitUntil: 'load' })
    tabs.push(page)
    await act(page)
  }
  for (const page of tabs) await act(page) // back and forth: every tab active again
  for (const page of tabs) await page.close({ runBeforeUnload: true })
  await sleep(SETTLE_MS)
  await context.close()
  return paths
}

async function main() {
  const browser = await chromium.launch({ executablePath: executablePath() })
  try {
    const first = await visit(browser, ['/demo', '/demo?page=2'])
    const second = await visit(browser, ['/demo'])
    await writeFile(args.out, JSON.stringify({ first, second }, null, 2))
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
