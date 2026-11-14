// The built app for the page tests: Vite builds it once per test file into a scratch folder, served the way the
// screenshot server serves dist/ (scripts/shots.mjs: the fixture /api and cake's /static/ player files), and
// Playwright's Chromium opens it. The samples the pages show are read from src/data/fixtures/ for the expectations.
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { build } from "vite"
import { launch, serve } from "../scripts/shots.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const fixtures = path.join(web, "src", "data", "fixtures")

/** A sample answer from src/data/fixtures/ ("session", "session/2b9e-c4", "replay/7f3a-c1/0"). */
export const sample = (name) => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf8"))

/** The sample detail of a session, wherever it lives. */
export function sessionSample(id) {
  const main = sample("session")
  return main.session.id === id ? main : sample(`session/${id}`)
}

export async function startApp() {
  const out = mkdtempSync(path.join(os.tmpdir(), "cake-web-test-"))
  await build({ root: web, configFile: path.join(web, "vite.config.ts"), logLevel: "silent", build: { outDir: out, emptyOutDir: true } })
  const server = await serve(out)
  const browser = await launch()
  const origin = `http://127.0.0.1:${server.address().port}`
  return {
    origin,
    browser,
    url: (route) => `${origin}/index.html${route}`,
    async close() {
      await browser.close()
      server.close()
      rmSync(out, { recursive: true, force: true })
    },
  }
}

/** A fresh tab at `width` (light, still: reduced motion), with every request it makes noted. */
export async function openTab(app, { width = 1280 } = {}) {
  const context = await app.browser.newContext({ viewport: { width, height: 900 }, colorScheme: "light", reducedMotion: "reduce" })
  const page = await context.newPage()
  const requests = []
  page.on("request", (request) => requests.push(request.url()))
  return { page, requests, close: () => context.close() }
}
