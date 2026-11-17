// demo_walk.mjs — a site's server half in a real browser (N1). Chromium through Playwright walks the test site's
// shop (tests/site, AgentCake's demo shop until 0.4.0; its pages signed with the secret of its own `agentcake serve`: a
// scratch CAKE_HOME and a free port): search, Classic T-shirt, Blue
// and M into the cart, the cart, checkout, done: six page requests. For each it notes the token in the response
// (Server-Timing), whether its Sec-Fetch values and header names are the ones Chrome sent (as Chrome's DevTools
// protocol records them: Network.requestWillBeSentExtraInfo, which lists the names sorted, so names are compared as a
// set; tests/test_demo_token.py pins their order), the token the page sees in its navigation entry (what cake.js
// reads) and what collect answered each batch of cake.js that carried it (X-Cake-Token: ok once, dup for a batch that
// was already on its way). Then it reads the srv table: every page's token must be kept for this session (N1: 100%).
// Two paces: settle waits on each page until collect has answered a batch carrying its token; brisk goes on as soon as
// each page has loaded, so a token may leave only with cake.js's exit send at pagehide (fetch keepalive), which
// DevTools does not show ("unseen"): there the srv table alone says what was kept.
//
//   node tests/browser/demo_walk.mjs [--out <folder>] [--paces settle,brisk] [--modes headless,headed]
//
// tests/browser/test_demo_walk.py runs it from the test suite. Playwright comes from web/node_modules (CAKE_PLAYWRIGHT:
// another playwright-core folder); the browser is Playwright's Chromium, found as web/scripts/shots.mjs finds it
// (chromium.mjs; CAKE_CHROME: another executable); cake runs on python3 (CAKE_PYTHON: another interpreter). Exit
// status 1 unless every page has a good token, kept for its session.
import { execFileSync, spawn } from "node:child_process"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import net from "node:net"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { startShop } from "./revisit_kit.mjs"
import zlib from "node:zlib"
import { executablePath } from "./chromium.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.join(here, "..", "..")
const require = createRequire(import.meta.url)
const { verifyToken } = require(path.join(repo, "edge", "node", "index.js"))
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, "web", "node_modules", "playwright-core"))

const PYTHON = process.env.CAKE_PYTHON || "python3"
const LOOPBACK = "127.0.0.1"
const SITE_KEY = "ck_demo_walk"  // the test site's pages carry it (tests/site/site_server.py)
const START_TIMEOUT_MS = 10000
const POLL_MS = 50
const HAND_OVER_TIMEOUT_MS = 10000 // cake.js sends every 2 s while it holds a token
const SRV_POLL_MS = 200
const SEC_FETCH = { s: "sec-fetch-site", m: "sec-fetch-mode", d: "sec-fetch-dest", u: "sec-fetch-user" }
const GZIP_MAGIC = Buffer.from([0x1f, 0x8b]) // cake.js gzips its bigger batches; collect knows them by these bytes
// The srv rows of one session, read with Python's sqlite3: Node 20 has no SQLite of its own.
const SRV_ROWS = "import json, sqlite3, sys\ncon = sqlite3.connect(sys.argv[1])\n" +
  "print(json.dumps(con.execute('SELECT id, path FROM srv WHERE session_id=? ORDER BY page_ms', (sys.argv[2],)).fetchall()))"
// Made-up details for the demo checkout (the page says to use made-up details; card fields are never recorded).
const ORDER = { email: "walker@example.com", fullname: "Demo Walker", address: "1 Example Street", city: "Sampleton",
  postcode: "00000", cardname: "Demo Walker", cardnumber: "4242 4242 4242 4242", expiry: "12/29", cvc: "123" }

// [what the visitor does, the page it lands on (path and query), how]
const STEPS = [
  ["open the shop", "/demo", (page, base) => page.goto(`${base}/demo`)],
  ["search for t-shirt", "/demo?q=t-shirt", async (page) => { await page.fill("#q", "t-shirt"); await page.press("#q", "Enter") }],
  ["open Classic T-shirt", "/demo/product?id=classic-tee", (page) => page.getByRole("link", { name: "Classic T-shirt", exact: true }).click()],
  ["choose Blue and M, add to cart, go to the cart", "/demo/cart", async (page) => {
    await page.check("input[name=color][value=Blue]")
    await page.selectOption("#size", "M")
    await page.click("#add")
    await page.getByRole("link", { name: "Go to cart" }).click()
  }],
  ["checkout", "/demo/checkout", (page) => page.click("#checkout")],
  ["fill in made-up details and place the order", "/demo/done", async (page) => {
    for (const [field, value] of Object.entries(ORDER)) await page.fill(`#${field}`, value)
    await page.selectOption("#country", "Other")
    await page.check("#agree")
    await page.click("#place")
  }],
]

function argument(name, fallback) {
  const at = process.argv.indexOf(name)
  return at === -1 ? fallback : process.argv[at + 1]
}

function today() {
  const d = new Date()
  return [d.getFullYear(), d.getMonth() + 1, d.getDate()].map((n) => String(n).padStart(2, "0")).join("-")
}

function launch(headless) {
  return chromium.launch({ executablePath: executablePath(), headless })
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const sameSet = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort())
const lower = (headers) => Object.fromEntries(Object.entries(headers || {}).map(([name, value]) => [name.toLowerCase(), value]))
const tokenIn = (serverTiming) => (/(?:^|,)\s*cake;desc="([^"]+)"/.exec(serverTiming || "") || [])[1] || null

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

// One `agentcake serve` of its own: a scratch CAKE_HOME, a free port and a secret, which the test site signs with.
async function startCake() {
  const home = mkdtempSync(path.join(os.tmpdir(), "agentcake-walk-"))
  const port = await freePort()
  for (const args of [["config", "set", "site_key", SITE_KEY], ["secret", "init"]]) {
    execFileSync(PYTHON, ["-I", path.join(repo, "agentcake", "__main__.py"), ...args],
      { env: { ...process.env, CAKE_HOME: home, CAKE_PORT: String(port) }, stdio: "ignore" })
  }
  const child = spawn(PYTHON, ["-I", path.join(repo, "agentcake", "__main__.py"), "serve"],
    { env: { ...process.env, CAKE_HOME: home, CAKE_PORT: String(port) }, stdio: ["ignore", "pipe", "pipe"] })
  let output = ""
  child.stdout.on("data", (chunk) => { output += chunk })
  child.stderr.on("data", (chunk) => { output += chunk })
  const cake = {
    base: `http://${LOOPBACK}:${port}`,
    siteKey: SITE_KEY,
    secretFile: path.join(home, "srv_secret"),
    secret: () => readFileSync(path.join(home, "srv_secret"), "utf8").trim(), // a scratch secret, never written down
    srvRows: (sessionId) => JSON.parse(execFileSync(PYTHON, ["-I", "-c", SRV_ROWS, path.join(home, "cake.db"), sessionId], { encoding: "utf8" })),
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

// Every main-frame document request, with the header lines Chrome sent (in their order) and the response's head.
function recordDocuments(cdp) {
  const byId = new Map()
  const order = []
  const entry = (id) => {
    if (!byId.has(id)) byId.set(id, {})
    return byId.get(id)
  }
  cdp.on("Network.requestWillBeSent", (event) => {
    if (event.type !== "Document") return
    Object.assign(entry(event.requestId), { url: event.request.url })
    order.push(event.requestId)
  })
  cdp.on("Network.requestWillBeSentExtraInfo", (event) => { entry(event.requestId).sent = event.headers })
  cdp.on("Network.responseReceivedExtraInfo", (event) => Object.assign(entry(event.requestId), { status: event.statusCode, received: lower(event.headers) }))
  return () => order.map((id) => byId.get(id))
}

// The token a batch of cake.js carries (its "st"), or null; a gzipped batch is unzipped first.
function tokenOfBatch(body) {
  if (!body) return null
  try {
    const text = body.subarray(0, GZIP_MAGIC.length).equals(GZIP_MAGIC) ? zlib.gunzipSync(body) : body
    return JSON.parse(text.toString("utf8")).st || null
  } catch {
    return null // not a batch cake.js sends
  }
}

// What collect answered (X-Cake-Token) for each token cake.js handed over; handedOver(token) waits for the first answer.
function watchCollect(context) {
  const answers = new Map()
  const waiting = new Map()
  context.on("response", (response) => {
    const request = response.request()
    if (request.method() !== "POST" || new URL(request.url()).pathname !== "/collect") return
    const token = tokenOfBatch(request.postDataBuffer())
    if (!token) return
    answers.set(token, [...(answers.get(token) || []), response.headers()["x-cake-token"] || `HTTP ${response.status()}`])
    if (waiting.has(token)) waiting.get(token)()
  })
  const handedOver = (token) => new Promise((resolve) => {
    if (answers.has(token)) return resolve(true)
    const timer = setTimeout(() => { waiting.delete(token); resolve(false) }, HAND_OVER_TIMEOUT_MS)
    waiting.set(token, () => { clearTimeout(timer); waiting.delete(token); resolve(true) })
  })
  return { answers, handedOver }
}

// The ids of the session's srv rows once they hold every one of ids, or when HAND_OVER_TIMEOUT_MS is up.
async function keptFor(cake, sessionId, ids) {
  const deadline = Date.now() + HAND_OVER_TIMEOUT_MS
  for (;;) {
    const kept = new Set(cake.srvRows(sessionId).map(([id]) => id))
    if (ids.every((id) => kept.has(id)) || Date.now() > deadline) return kept
    await pause(SRV_POLL_MS)
  }
}

async function seenByPage(page) {
  return page.evaluate(() => {
    const entry = performance.getEntriesByType("navigation")[0]
    const cake = entry.serverTiming.find((each) => each.name === "cake")
    return { type: entry.type, token: cake ? cake.description : null }
  })
}

// What one page request was: its token, checked against the secret and against what Chrome sent and the page sees.
async function pageRecord(step, landsOn, request, pageSees, cake, tokensSoFar) {
  const token = tokenIn(request.received && request.received["server-timing"])
  const verified = token ? await verifyToken(cake.secret(), token) : { result: "no token" }
  const sent = lower(request.sent)
  const secFetchSent = Object.fromEntries(Object.entries(SEC_FETCH).map(([key, name]) => [key, name in sent ? sent[name] : null]))
  const namesSent = Object.keys(sent)
  const p = verified.payload || {}
  const seen = pageSees.token === null ? "none" : pageSees.token === token ? "this response's"
    : tokensSoFar.includes(pageSees.token) ? "an earlier response's" : "unknown"
  return {
    step,
    path: landsOn,
    status: request.status ?? null,
    token,
    token_id: p.id ?? null,
    token_verifies: verified.result,
    token_path: p.p ?? null,
    sec_fetch_sent: secFetchSent,
    sec_fetch_in_token: p.sf ?? null,
    sec_fetch_same: JSON.stringify(secFetchSent) === JSON.stringify(p.sf),
    header_names_sent: namesSent,
    header_names_in_token: p.hn ?? null,
    header_names_same_set: sameSet(namesSent, p.hn),
    network_key_in_token: typeof p.ik === "string",
    page_navigation_type: pageSees.type,
    token_the_page_sees: seen,
  }
}

async function walk(cake, mode, pace, out) {
  const browser = await launch(mode === "headless")
  const steps = []
  let collect = null
  let kept = new Set()
  try {
    const context = await browser.newContext()
    const page = await context.newPage()
    const cdp = await context.newCDPSession(page)
    await cdp.send("Network.enable")
    const documents = recordDocuments(cdp)
    collect = watchCollect(context)
    for (const [step, landsOn, go] of STEPS) {
      const before = documents().length
      await go(page, cake.shop.url)
      await page.waitForURL((url) => url.pathname + url.search === landsOn, { waitUntil: "load" })
      const request = documents().slice(before).pop() || {}
      const record = await pageRecord(step, landsOn, request, await seenByPage(page), cake, steps.map((s) => s.token))
      steps.push(record)
      if (pace === "settle" && record.token) await collect.handedOver(record.token)
      if (pace === "settle" && ["/demo/cart", "/demo/done"].includes(landsOn)) {
        await page.screenshot({ path: path.join(out, `walk-${mode}-${landsOn.split("/").pop()}.png`) })
      }
    }
    const sessionId = await page.evaluate(() => sessionStorage.getItem("cake_sid"))
    if (pace === "brisk") await page.goto("about:blank") // the done page's token leaves with its pagehide send
    // while the browser is still open, so its last pagehide send is not cut off
    kept = await keptFor(cake, sessionId, steps.map((s) => s.token_id).filter(Boolean))
    await context.close()
  } finally {
    await browser.close()
  }
  for (const s of steps) {
    s.collect_answered = collect.answers.get(s.token) || []
    s.kept_for_this_session = kept.has(s.token_id)
    delete s.token // the report keeps token ids, not tokens
  }
  const matched = steps.filter((s) => s.kept_for_this_session).length
  return { mode, pace, pages: steps.length, kept_for_this_session: matched, n1: matched / steps.length, srv_rows_for_this_session: kept.size, steps }
}

const isGood = (s) => s.token_verifies === "ok" && s.sec_fetch_same && s.header_names_same_set && s.kept_for_this_session

function describe(mode, pace, s) {
  const head = `${mode.padEnd(8)} ${pace.padEnd(6)} ${s.path.padEnd(28)} ${String(s.status).padEnd(4)}`
  if (s.token_verifies === "no token") return `${head} NO TOKEN; page sees ${s.token_the_page_sees}`
  return `${head} token ${s.token_verifies}, sec-fetch ${s.sec_fetch_same ? "same" : "DIFFERENT"}, header names ` +
    `${s.header_names_same_set ? "same" : "DIFFERENT"}; page sees ${s.token_the_page_sees}; ` +
    `collect ${s.collect_answered.join(",") || "unseen"}; kept ${s.kept_for_this_session ? "yes" : "NO"}`
}

async function main() {
  const out = path.resolve(argument("--out", path.join(os.tmpdir(), "agentcake-evidence", today(), "demo-walk")))
  const paces = argument("--paces", "settle,brisk").split(",")
  const modes = argument("--modes", "headless").split(",")
  mkdirSync(out, { recursive: true })
  const cake = await startCake()
  cake.shop = await startShop(cake)
  const report = { browser: null, walks: [] }
  let failures = 0
  try {
    for (const mode of modes) {
      for (const pace of paces) {
        const result = await walk(cake, mode, pace, out)
        report.walks.push(result)
        for (const s of result.steps) {
          if (!isGood(s)) failures++
          console.log(describe(mode, pace, s))
        }
        console.log(`${mode} ${pace}: N1 ${result.kept_for_this_session}/${result.pages} (${(result.n1 * 100).toFixed(0)}%), srv rows for this session ${result.srv_rows_for_this_session}`)
      }
    }
    const browser = await launch(true)
    report.browser = browser.version()
    await browser.close()
  } finally {
    await cake.shop.stop()
    await cake.stop()
  }
  writeFileSync(path.join(out, "demo-walk.json"), `${JSON.stringify(report, null, 2)}\n`)
  console.log(`${failures ? `${failures} page(s) without a good token kept for the session` : "every page: a good token with the Sec-Fetch values and header names Chrome sent, kept for the session (N1 100%)"} (${report.browser})`)
  process.exitCode = failures ? 1 : 0
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
