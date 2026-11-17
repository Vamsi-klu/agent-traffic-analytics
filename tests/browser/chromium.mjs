// The Chromium every browser script of these tests launches, one rule for all of them: CAKE_CHROME when it is set;
// else the Chrome for Testing build in Playwright's cache on macOS x64 (chromium-1228, what the lab's runs use);
// else the browser playwright-core installs for itself (executablePath undefined: playwright-core picks it).
//
//   node tests/browser/chromium.mjs   starts that Chromium headless and closes it: exit 0 when it starts, else 1 with
//                                     why. tests/browser/harness.py missing() runs it, so that a browser test on a
//                                     computer without one is skipped and says so instead of failing.
//
// playwright-core comes from CAKE_PLAYWRIGHT or web/node_modules/playwright-core, as for the other scripts.
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const CACHED = path.join(os.homedir(), 'Library/Caches/ms-playwright/chromium-1228',
  'chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')

export function executablePath() {
  return process.env.CAKE_CHROME || (existsSync(CACHED) ? CACHED : undefined)
}

async function check() {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
  const playwright = process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core')
  const { chromium } = createRequire(import.meta.url)(playwright)
  try {
    const browser = await chromium.launch({ executablePath: executablePath() })
    await browser.close()
  } catch (error) {
    console.error(String(error.message || error).split('\n')[0])
    process.exit(1)
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await check()
