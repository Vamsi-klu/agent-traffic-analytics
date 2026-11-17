// The registration card end to end, driven by tests/browser/test_register_walk.py: a real AgentCake with
// the built local pages, opened in Chromium. Usage: node register_walk.mjs --base <AgentCake's local page> --out <dir>
//   --scenario sent      fill the card, open "View registration data", note its text, press "Register and continue", wait for
//                        the pages (the home page's onboarding)
//   --scenario not-sent  fill the card, press, wait for the card to say why it wasn't sent, press Continue, wait for
//                        the pages, open the page again and wait for the card
// Prints its report ({scenario, steps, shown, alert}) as one JSON line and keeps a screenshot per step in <dir>.
// playwright-core comes from CAKE_PLAYWRIGHT or web/node_modules/playwright-core, Chromium from CAKE_CHROME or
// Playwright's cache (chromium.mjs).
import { mkdir } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { executablePath } from './chromium.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, a, i, all) => (a.startsWith('--') ? [...pairs, [a.slice(2), all[i + 1]]] : pairs), []))
const playwright = process.env.CAKE_PLAYWRIGHT || path.join(here, '..', '..', 'web', 'node_modules', 'playwright-core')
const { chromium } = createRequire(import.meta.url)(playwright)
const WAIT_MS = 20000
const EMAIL = 'owner@example.com'
const COMPANY = 'Bäckerei Ünal'

function launch() {
  return chromium.launch({ executablePath: executablePath() })
}

const browser = await launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' })
await mkdir(args.out, { recursive: true })
const report = { scenario: args.scenario, steps: [], shown: null, alert: null }
const step = async (name) => {
  report.steps.push(name)
  await page.screenshot({ path: path.join(args.out, `${args.scenario}-${report.steps.length}-${name}.png`), fullPage: true })
}
const welcome = () => page.getByRole('heading', { level: 1, name: /^Welcome to / })

try {
  await page.goto(args.base + '/')
  await welcome().waitFor({ timeout: WAIT_MS })
  await step('card')
  await page.getByLabel('Email address').fill(EMAIL)
  await page.getByLabel('Company (optional)').fill(COMPANY)
  if (args.scenario === 'sent') {
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: "View registration data" }).click()
    report.shown = await page.getByLabel("Registration data").locator('pre').innerText()
    await step('what-is-sent')
    await page.getByRole('button', { name: 'Register and continue' }).click()
    await page.getByRole('heading', { name: 'Install with your AI agent' }).waitFor({ timeout: WAIT_MS })
    await step('pages')
  } else {
    await page.getByRole('button', { name: 'Register and continue' }).click()
    const alert = page.getByRole('form').getByRole('alert')
    await alert.waitFor({ timeout: WAIT_MS })
    report.alert = await alert.innerText()
    await step('not-sent')
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('heading', { name: 'Install with your AI agent' }).waitFor({ timeout: WAIT_MS })
    await step('pages')
    await page.reload()
    await welcome().waitFor({ timeout: WAIT_MS })
    await step('asked-again')
  }
} finally {
  await browser.close()
}
console.log(JSON.stringify(report))
