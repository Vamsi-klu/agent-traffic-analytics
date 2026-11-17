// revisit_kit.mjs — what token_revisits.mjs needs around the browsers: a scratch `agentcake serve` with a site key
// and a secret of its own, its database read through Python's sqlite3 (Node 20 has no SQLite), the browsers, and the
// small readers of what cake.js sends. Like tests/browser/demo_walk.mjs, cake gets its own CAKE_HOME and a free port of
// 127.0.0.1, so a person's own cake (~/.cake, its port) is never touched.
import { execFileSync, spawn } from "node:child_process"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { createRequire } from "node:module"
import net from "node:net"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import zlib from "node:zlib"
import { executablePath } from "./chromium.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.join(here, "..", "..")
const require = createRequire(import.meta.url)
const playwright = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, "web", "node_modules", "playwright-core"))

const PYTHON = process.env.CAKE_PYTHON || "python3"
const AGENTCAKE = path.join(repo, "agentcake", "__main__.py")
const LOOPBACK = "127.0.0.1"
const SITE_KEY = "ck_revisits"
const START_TIMEOUT_MS = 10000
const POLL_MS = 50
const GZIP_MAGIC = Buffer.from([0x1f, 0x8b]) // cake.js gzips its bigger batches; collect knows them by these bytes
const QUERY = "import json, sqlite3, sys\ncon = sqlite3.connect(sys.argv[1])\n" +
  "print(json.dumps(con.execute(sys.argv[2], json.loads(sys.argv[3])).fetchall()))"
// Playwright's Chromium as web/scripts/shots.mjs finds it; WebKit and Firefox from Playwright's own cache.

export const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
export const tokenIn = (serverTiming) => (/(?:^|,)\s*cake;desc="([^"]+)"/.exec(serverTiming || "") || [])[1] || null

export function argument(name, fallback) {
  const at = process.argv.indexOf(name)
  return at === -1 ? fallback : process.argv[at + 1]
}

export function today() {
  const d = new Date()
  return [d.getFullYear(), d.getMonth() + 1, d.getDate()].map((n) => String(n).padStart(2, "0")).join("-")
}

// The headless launch options of a browser by name: chromium (as Playwright starts it: no back-forward cache),
// chromium-bfcache (the back-forward cache on, as Chrome ships), webkit, firefox.
function optionsOf(name) {
  if (!name.startsWith("chromium")) return [playwright[name], { headless: true }]
  const ignoreDefaultArgs = name === "chromium-bfcache" ? ["--disable-back-forward-cache"] : []
  return [playwright.chromium, { executablePath: executablePath(), headless: true, ignoreDefaultArgs }]
}

// The browser's version, or an error when it is not installed.
export async function versionOf(name) {
  const [type, options] = optionsOf(name)
  const browser = await type.launch(options)
  const version = browser.version()
  await browser.close()
  return version
}

// A browser context with a profile of its own on disk, so it has an HTTP cache on disk as a person's browser does
// (Playwright's WebKit keeps nothing in the cache of a context made with newContext(): it never sends a 304's
// If-None-Match). close() ends the browser and removes the profile.
export async function openContext(name) {
  const [type, options] = optionsOf(name)
  const profile = mkdtempSync(path.join(os.tmpdir(), "agentcake-revisits-profile-"))
  const context = await type.launchPersistentContext(profile, options)
  return { context, close: async () => { await context.close(); rmSync(profile, { recursive: true, force: true }) } }
}

// The batch an upload of cake.js holds, or null; a gzipped one is unzipped first.
export function batchOf(body) {
  if (!body) return null
  try {
    const text = body.subarray(0, GZIP_MAGIC.length).equals(GZIP_MAGIC) ? zlib.gunzipSync(body) : body
    const batch = JSON.parse(text.toString("utf8"))
    return batch && typeof batch === "object" ? batch : null
  } catch {
    return null // not a batch cake.js sends
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.on("error", reject)
    server.listen(0, LOOPBACK, () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

// One `agentcake serve` of its own: a scratch CAKE_HOME with a site key and `secret init`, on a free port.
/** The test site's shop (tests/site/site_server.py: AgentCake's demo shop until 0.4.0) on a free port, its pages loading
 *  this cake's cake.js and signed with its secret, as the demo shop's were: { url, stop }. */
export async function startShop(cake) {
  const child = spawn(PYTHON, ["-I", path.join(repo, "tests", "site", "site_server.py"), "--cake", cake.base,
    "--site-key", cake.siteKey, "--secret-file", cake.secretFile], { stdio: ["ignore", "pipe", "inherit"] })
  const url = await new Promise((resolve, reject) => {
    child.stdout.once("data", (chunk) => resolve(String(chunk).trim()))
    child.once("exit", (code) => reject(new Error(`the test site stopped (${code})`)))
  })
  return { url, stop: async () => { if (child.exitCode === null) { child.kill("SIGTERM"); await new Promise((r) => child.once("exit", r)) } } }
}

export async function startCake() {
  const home = mkdtempSync(path.join(os.tmpdir(), "agentcake-revisits-"))
  const env = { ...process.env, CAKE_HOME: home, CAKE_PORT: String(await freePort()) }
  for (const args of [["config", "set", "site_key", SITE_KEY], ["secret", "init"]]) {
    execFileSync(PYTHON, ["-I", AGENTCAKE, ...args], { env, stdio: "ignore" })
  }
  const child = spawn(PYTHON, ["-I", AGENTCAKE, "serve"], { env, stdio: ["ignore", "pipe", "pipe"] })
  let output = ""
  child.stdout.on("data", (chunk) => { output += chunk })
  child.stderr.on("data", (chunk) => { output += chunk })
  const defaults = JSON.parse(readFileSync(path.join(repo, "agentcake", "defaults.json"), "utf8"))
  const cake = {
    base: `http://${LOOPBACK}:${env.CAKE_PORT}`,
    siteKey: SITE_KEY,
    secret: () => readFileSync(path.join(home, "srv_secret"), "utf8").trim(), // a scratch secret, never written down
    secretFile: path.join(home, "srv_secret"),
    maxAgeMs: () => defaults.token_max_age_ms.default,
    rows: (sql, args) => JSON.parse(execFileSync(PYTHON, ["-I", "-c", QUERY, path.join(home, "cake.db"), sql, JSON.stringify(args)], { encoding: "utf8" })),
    stop: async () => {
      if (child.exitCode === null) {
        child.kill("SIGTERM")
        await new Promise((resolve) => child.once("exit", resolve))
      }
      rmSync(home, { recursive: true, force: true })
    },
  }
  const deadline = Date.now() + START_TIMEOUT_MS
  while (Date.now() < deadline && child.exitCode === null) {
    try {
      if ((await fetch(`${cake.base}/api/health`)).ok) return cake
    } catch {
      // not listening yet
    }
    await pause(POLL_MS)
  }
  await cake.stop()
  throw new Error(`agentcake serve did not answer within ${START_TIMEOUT_MS} ms: ${output}`)
}
