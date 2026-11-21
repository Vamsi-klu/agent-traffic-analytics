// cross_origin.mjs — the subdomain route in a real browser: the website's pages on one origin, AgentCake on another.
// A scratch `agentcake serve` (its own CAKE_HOME and free ports) runs with the server settings of the subdomain route:
// the public listener on 127.0.0.1, path_prefix /cake, trust_lb, site_domain example.localhost and public_url
// http://cake.example.localhost:<port>. In front of it a stand-in for Caddy (deploy/Caddyfile) forwards only the page
// script and collect, answers 404 to anything else, writes the visitor's address and protocol into the headers
// AgentCake trusts, removes the others, and counts every request it gets by method. Every page of the test website
// carries exactly the line the settings API gives (script_tag), so it loads cake.js from the subdomain. Chromium opens
// the website on www.example.localhost (*.localhost is this computer to Chrome), stays, follows a link to a second
// page and stays again; then the same from shop.elsewhere.localhost, a site that is not the website. Written to
// <out>/cross-origin.json: per visit, every upload the browser made (answered, failed, copies of a batch already sent),
// the batches parked in sessionStorage at the end, CORS errors in the console; the requests the front door got, a
// preflight among them, and the batches it passed on, counted again there because the browser's own list can miss the
// keepalive batches a page sends as it is left; and what AgentCake kept: the session's origin, and whether the session
// list shows it. Nothing leaves 127.0.0.1.
//
//   node tests/browser/cross_origin.mjs --out <folder>      (playwright-core: CAKE_PLAYWRIGHT; Chromium: chromium.mjs)
import { execFileSync, spawn } from "node:child_process"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import http from "node:http"
import { createRequire } from "node:module"
import net from "node:net"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { executablePath } from "./chromium.mjs"
import { argument, batchOf, pause } from "./revisit_kit.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.join(here, "..", "..")
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, "web", "node_modules", "playwright-core"))
const data = (name) => JSON.parse(readFileSync(path.join(repo, "agentcake", "data", name), "utf8"))
const LB_HEADERS = data("lb_headers.json").headers // what AgentCake believes with trust_lb (netfacts.py)
const STORAGE = data("cakejs.json").script.storage // cake.js's sessionStorage keys: the session id, parked batches
const PYTHON = process.env.CAKE_PYTHON || "python3"
const AGENTCAKE = path.join(repo, "agentcake", "__main__.py")
const LOOPBACK = "127.0.0.1"
const SITE_KEY = "ck_crossorigin"
const PREFIX = "/cake"
const SITE_DOMAIN = "example.localhost"
const VISITS = [["site", `www.${SITE_DOMAIN}`], ["other", "shop.elsewhere.localhost"]] // the website, then another site
const ANSWERED = 204 // collect's answer to a batch it took
const DWELL_MS = 6000 // cake.js sends every 2 s and sends a batch again on its next tick: three ticks on each page
const FIRST_UPLOAD_TIMEOUT_MS = 30000
const START_TIMEOUT_MS = 15000
const POLL_MS = 50
const QUERY = "import json, sqlite3, sys\ncon = sqlite3.connect(sys.argv[1])\n" +
  "print(json.dumps(con.execute(sys.argv[2], json.loads(sys.argv[3])).fetchall()))"

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.on("error", reject)
    server.listen(0, LOOPBACK, () => { const { port } = server.address(); server.close(() => resolve(port)) })
  })
}

function listen(server) {
  return new Promise((resolve) => server.listen(0, LOOPBACK, () => resolve(server.address().port)))
}

async function until(test, timeoutMs, what) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await test()) return
    await pause(POLL_MS)
  }
  throw new Error(`${what} within ${timeoutMs} ms`)
}

/** `agentcake serve` with the subdomain route's settings; public_url names the front door, which isn't up yet. */
async function startCake(frontPort) {
  const home = mkdtempSync(path.join(os.tmpdir(), "agentcake-cross-origin-"))
  const [localPort, publicPort] = [await freePort(), await freePort()]
  const env = { ...process.env, CAKE_HOME: home, CAKE_PORT: String(localPort) }
  for (const [key, value] of [["site_key", SITE_KEY], ["public_listen", `${LOOPBACK}:${publicPort}`], ["path_prefix", PREFIX],
    ["trust_lb", "true"], ["site_domain", SITE_DOMAIN], ["public_url", `http://cake.${SITE_DOMAIN}:${frontPort}`],
    ["lists_auto_update", "false"]]) {  // a test never goes online (agentcake/updates.py)
    execFileSync(PYTHON, ["-I", AGENTCAKE, "config", "set", key, value], { env, stdio: "ignore" })
  }
  const child = spawn(PYTHON, ["-I", AGENTCAKE, "serve"], { env, stdio: ["ignore", "pipe", "pipe"] })
  let output = ""
  child.stdout.on("data", (chunk) => { output += chunk })
  child.stderr.on("data", (chunk) => { output += chunk })
  const local = `http://${LOOPBACK}:${localPort}`
  const cake = {
    local, publicPort,
    get: async (route) => (await fetch(local + route)).json(),
    rows: (sql, args) => JSON.parse(execFileSync(PYTHON, ["-I", "-c", QUERY, path.join(home, "cake.db"), sql, JSON.stringify(args)],
      { encoding: "utf8" })),
    stop: async () => {
      if (child.exitCode === null) { child.kill("SIGTERM"); await new Promise((resolve) => child.once("exit", resolve)) }
      rmSync(home, { recursive: true, force: true })
      return output
    },
  }
  await until(async () => {
    if (child.exitCode !== null) throw new Error(`agentcake serve stopped: ${output}`)
    try { return (await fetch(`${local}/api/health`)).ok } catch { return false }
  }, START_TIMEOUT_MS, "agentcake serve did not answer")
  return cake
}

/** The stand-in for Caddy in front of AgentCake's public listener, on frontPort. */
async function startFrontDoor(frontPort, publicPort, forwarded) {
  const requests = []
  const server = http.createServer((request, answer) => {
    const where = new URL(request.url, "http://front.door").pathname
    const seen = { method: request.method, path: where, batch: null }
    requests.push(seen)
    const body = []
    request.on("data", (chunk) => body.push(chunk))
    request.on("end", () => {
      const batch = batchOf(Buffer.concat(body))
      seen.batch = batch ? `${batch.pv}:${batch.seq}` : null
    })
    if (!forwarded.includes(where)) { answer.writeHead(404); answer.end(); return }
    const headers = { ...request.headers }
    for (const name of Object.values(LB_HEADERS)) delete headers[name.toLowerCase()]
    headers[LB_HEADERS.ip.toLowerCase()] = request.socket.remoteAddress
    headers[LB_HEADERS.proto.toLowerCase()] = `HTTP/${request.httpVersion}`
    const upstream = http.request({ host: LOOPBACK, port: publicPort, method: request.method, path: request.url, headers }, (reply) => {
      answer.writeHead(reply.statusCode, reply.headers)
      reply.pipe(answer)
    })
    upstream.on("error", () => { answer.writeHead(502); answer.end() })
    request.pipe(upstream)
  })
  await new Promise((resolve) => server.listen(frontPort, LOOPBACK, resolve))
  return { requests, close: () => server.close() }
}

/** The test website: two pages, each with the line in its head, linking to each other. */
async function startSite(line) {
  const page = (title, next) => `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>${line}</head>` +
    `<body><h1>${title}</h1><p>A page of the website.</p><a id="next" href="${next}">Next page</a></body></html>`
  const server = http.createServer((request, answer) => {
    answer.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" })
    answer.end(request.url.startsWith("/next") ? page("Second page", "/") : page("Home", "/next"))
  })
  return { port: await listen(server), close: () => server.close() }
}

async function visit(browser, cake, front, site, [name, host], collectPath) {
  const context = await browser.newContext()
  const page = await context.newPage()
  const uploads = [], corsErrors = []
  page.on("request", (request) => {
    if (new URL(request.url()).pathname !== collectPath) return
    const batch = batchOf(request.postDataBuffer())
    uploads.push({ request, method: request.method(), id: batch ? `${batch.pv}:${batch.seq}` : null, status: null, failed: null })
  })
  page.on("requestfinished", async (request) => {
    const upload = uploads.find((u) => u.request === request)
    if (upload) upload.status = (await request.response())?.status() ?? null
  })
  page.on("requestfailed", (request) => {
    const upload = uploads.find((u) => u.request === request)
    if (upload) upload.failed = request.failure()?.errorText || "failed"
  })
  page.on("console", (message) => { if (/CORS|Access-Control/.test(message.text())) corsErrors.push(message.text()) })
  const before = front.requests.length
  const origin = `http://${host}:${site.port}`
  for (const where of ["/", "/next"]) {
    const answeredBefore = uploads.filter((u) => u.status === ANSWERED).length
    if (where === "/") await page.goto(`${origin}/`)
    else await page.click("#next")
    await until(() => uploads.filter((u) => u.status === ANSWERED).length > answeredBefore, FIRST_UPLOAD_TIMEOUT_MS,
      `no upload of ${origin}${where} was answered`)
    await pause(DWELL_MS)
  }
  const stored = await page.evaluate((keys) => ({ session: sessionStorage.getItem(keys.session), parked: sessionStorage.getItem(keys.pending) }), STORAGE)
  const scriptSrc = await page.evaluate(() => document.querySelector("script[data-site]").src)
  await context.close()
  const posts = uploads.filter((u) => u.method === "POST")
  const ids = posts.map((u) => u.id).filter(Boolean)
  const atTheDoor = front.requests.slice(before)
  const passedOn = atTheDoor.map((r) => r.batch).filter(Boolean)
  const session = stored.session
  const kept = cake.rows("SELECT origin FROM sessions WHERE id = ?", [session])
  const listed = (await cake.get("/api/sessions")).results.map((row) => row.id)
  return {
    name, page: origin, script_src: scriptSrc,
    browser: {
      uploads: posts.length,
      answered: posts.filter((u) => u.status === ANSWERED && !u.failed).length,
      other_statuses: [...new Set(posts.filter((u) => u.status !== null && u.status !== ANSWERED).map((u) => u.status))],
      failed: posts.filter((u) => u.failed).map((u) => u.failed),
      copies_of_a_batch_already_sent: ids.length - new Set(ids).size,
      parked_at_the_end: stored.parked ? JSON.parse(stored.parked).length : 0,
      preflights: uploads.filter((u) => u.method === "OPTIONS").length,
      console_cors_errors: corsErrors,
    },
    front_door: {
      requests: atTheDoor.length,
      by_method: atTheDoor.reduce((count, r) => ({ ...count, [r.method]: (count[r.method] || 0) + 1 }), {}),
      not_forwarded: atTheDoor.filter((r) => r.path !== collectPath && r.path !== new URL(scriptSrc).pathname).length,
      batches: passedOn.length,
      copies_of_a_batch_already_sent: passedOn.length - new Set(passedOn).size,
    },
    agentcake: { session_kept: kept.length === 1, origin: kept.length ? kept[0][0] : null, in_the_session_list: listed.includes(session) },
  }
}

async function main() {
  const out = argument("--out", null)
  if (!out) throw new Error("usage: node cross_origin.mjs --out <folder>")
  mkdirSync(out, { recursive: true })
  const frontPort = await freePort()
  const cake = await startCake(frontPort)
  let front = null, site = null, browser = null
  try {
    const { script_tag: line, site_domain: domain } = await cake.get("/api/settings")
    const scriptSrc = /src="([^"]+)"/.exec(line)[1]
    const collectPath = new URL(data("cakejs.json").script.collect_path, scriptSrc).pathname
    front = await startFrontDoor(frontPort, cake.publicPort, [new URL(scriptSrc).pathname, collectPath])
    site = await startSite(line)
    browser = await chromium.launch({ executablePath: executablePath(), headless: true })
    const visits = []
    for (const which of VISITS) visits.push(await visit(browser, cake, front, site, which, collectPath))
    const report = { browser: browser.version(), line, site_domain: domain, visits }
    writeFileSync(path.join(out, "cross-origin.json"), JSON.stringify(report, null, 1) + "\n")
    for (const v of visits) {
      console.log(`${v.name.padEnd(5)} ${v.page}: ${v.browser.answered}/${v.browser.uploads} uploads answered, ` +
        `${v.front_door.copies_of_a_batch_already_sent} copies of ${v.front_door.batches} batches at the door, ` +
        `${v.browser.parked_at_the_end} parked, ` +
        `${v.front_door.by_method.OPTIONS || 0} preflights; kept as ${v.agentcake.origin}, ` +
        `${v.agentcake.in_the_session_list ? "listed" : "not listed"}`)
    }
  } finally {
    await browser?.close()
    site?.close()
    front?.close()
    const output = await cake.stop()
    if (/Traceback/.test(output)) console.error(output)
  }
}

await main()
