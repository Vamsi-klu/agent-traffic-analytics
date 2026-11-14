// Records the sample sessions' replays: real rrweb events, recorded by cake.js in the test site's shop (tests/site,
// the demo shop until 0.4.0), read back from
// Agent Cake's database, written as the sample answers of GET /api/session/<id>/replay?chunk=<n>.
//
//   cd web && node scripts/replay-fixtures.mjs        (about three minutes: the walks take as long as the sessions)
//
// It starts its own Agent Cake (bin/agentcake serve, a scratch CAKE_HOME, a free port, a secret) and the test site
// (tests/site/site_server.py on a free port, its pages signed with that secret), walks the shop once per
// sample session in Playwright's Chromium (scripts/replay-walks.mjs), reads each session's rrweb events page by page
// (streams.read_events with_page: each page view's events, which must follow one another in time, one tab) and its
// server half from the srv table, and writes
//   src/data/fixtures/replay/<id>/<n>.json   one file per chunk, cut the way cake cuts them (chunk_ms windows of the
//                                            events' own clock, agentcake/data/storage.json)
//   the session's sample (fixtures/session.json or fixtures/session/<id>.json): replay (epoch_ms, chunks, start_url),
//                                            actions (what the walk did) and server.pages; the rest is hand-written.
// The scratch cake's and the test site's addresses become the default one, its site key a placeholder, and the demo checkout's sample card
// number the wording the shop's checkout gives it; the files the recorded stylesheets ask for (the shop's fonts) become
// root-relative, so a sample replays them from whichever server shows it (the dev, screenshot and test servers serve
// /demo/ as cake does) and never asks an address of this computer; then every file is checked for what must never be
// there (what was typed, card numbers, the scratch folder, port and key). Playwright and Chromium: as scripts/shots.mjs
// finds them.
import { execFileSync, spawn } from "node:child_process"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import net from "node:net"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { DEFAULT_PORT, RRWEB, SITE_KEY_PLACEHOLDER, chunksOf, forbidden, pageViews, serverPage } from "./replay-samples.mjs"
import { TYPED, VIEWPORT, WALKS, walker } from "./replay-walks.mjs"
import { launch } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const web = path.join(here, ".."), repo = path.join(web, "..")
const fixtures = path.join(web, "src", "data", "fixtures")
const readJson = (file) => JSON.parse(readFileSync(file, "utf8"))
const LOOPBACK = "127.0.0.1" // protocol: the local page only ever listens on the loopback address
const CARD_HINT = ["Any made-up number works, e.g. 4242 4242 4242 4242.", "Any made-up card number works."] // the shop's wording
const POLL_MS = 500, SETTLE_POLLS = 3, START_TIMEOUT_MS = 15000
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// The session list, and one session's rrweb events and server half, read with cake's own code.
const READ = `import json, sys
sys.path.insert(0, sys.argv[1])
from agentcake import store, streams
con = store.db()
out = {"sessions": [r[0] for r in con.execute("SELECT id FROM sessions ORDER BY start_ms")]}
if len(sys.argv) > 2:
    sid = sys.argv[2]
    out["events"] = [[ts, text, page] for ts, _, text, page in streams.read_events(con, sid, ["rrweb"], with_page=True)]
    out["srv"] = [list(r) for r in con.execute("SELECT page_ms, path, body, net_match, ua_match, lang_match, reuses FROM srv WHERE session_id=? ORDER BY page_ms", (sid,))]
print(json.dumps(out))`

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer().on("error", reject)
    server.listen(0, LOOPBACK, () => { const { port } = server.address(); server.close(() => resolve(port)) })
  })
}

async function startCake() {
  const home = mkdtempSync(path.join(os.tmpdir(), "agentcake-replays-")), port = await freePort()
  const env = { ...process.env, CAKE_HOME: home, CAKE_PORT: String(port) }
  execFileSync(path.join(repo, "bin", "agentcake"), ["secret", "init"], { env, stdio: "ignore" })
  const child = spawn(path.join(repo, "bin", "agentcake"), ["serve"], { env, stdio: ["ignore", "pipe", "pipe"] })
  let output = ""
  child.stdout.on("data", (c) => { output += c }); child.stderr.on("data", (c) => { output += c })
  const base = `http://${LOOPBACK}:${port}`
  for (const started = Date.now(); ; await sleep(POLL_MS)) {
    if (await fetch(`${base}/api/health`).then((r) => r.ok, () => false)) break
    if (child.exitCode !== null || Date.now() - started > START_TIMEOUT_MS) throw new Error(`Agent Cake did not start:\n${output}`)
  }
  const siteKey = () => readJson(path.join(home, "config.json")).site_key
  const site = spawn("python3", ["-I", path.join(repo, "tests", "site", "site_server.py"), "--cake", base, "--site-key", siteKey(),
    "--secret-file", path.join(home, "srv_secret")], { stdio: ["ignore", "pipe", "inherit"] })
  const shop = await new Promise((resolve) => site.stdout.once("data", (line) => resolve(String(line).trim())))
  const read = (sid) => JSON.parse(execFileSync("python3", ["-I", "-B", "-c", READ, repo, ...(sid ? [sid] : [])], { env, encoding: "utf8", maxBuffer: 1 << 28 }))
  const stop = async () => {
    if (site.exitCode === null) site.kill("SIGTERM")
    if (child.exitCode === null) { child.kill("SIGTERM"); await new Promise((resolve) => child.once("exit", resolve)) }
    rmSync(home, { recursive: true, force: true })
  }
  return { home, port, base, shop, shopPort: new URL(shop).port, read, stop, siteKey }
}

/** Walk once, close the tab at the session's end, and wait until its last upload is in: the new session's id. */
async function record(cake, browser, walk) {
  const before = new Set(cake.read().sessions)
  const context = await browser.newContext({ viewport: VIEWPORT })
  const page = await context.newPage()
  const t0 = Date.now()
  const steps = walker(page, t0, walk.seed)
  await walk.run(steps, cake.shop)
  await steps.at(walk.duration_ms)
  await page.goto("about:blank") // pagehide: cake.js sends what it still holds, and records nothing more
  await context.close()
  let id = null, last = -1, still = 0
  while (still < SETTLE_POLLS) {
    await sleep(POLL_MS)
    id ??= cake.read().sessions.find((s) => !before.has(s)) ?? null
    const count = id ? cake.read(id).events.length : 0
    still = count > 0 && count === last ? still + 1 : 0
    last = count
  }
  return { id, t0, actions: steps.actions }
}

/** The scratch cake's address, key and the shop's sample card number out of one event's JSON text; a stylesheet's
 *  url("<the scratch cake>/…") becomes url("/…") (rrweb writes each stylesheet's addresses out in full). */
function clean(text, cake) {
  return text.replaceAll(`url(\\"http://${LOOPBACK}:${cake.port}/`, `url(\\"/`).replaceAll(`url(\\"http://${LOOPBACK}:${cake.shopPort}/`, `url(\\"/`)
    .replaceAll(`${LOOPBACK}:${cake.port}`, `${LOOPBACK}:${DEFAULT_PORT}`).replaceAll(`${LOOPBACK}:${cake.shopPort}`, `${LOOPBACK}:${DEFAULT_PORT}`).replaceAll(cake.siteKey(), SITE_KEY_PLACEHOLDER).replaceAll(...CARD_HINT)
}

const samplePath = (id) => {
  const main = path.join(fixtures, "session.json")
  return readJson(main).session.id === id ? main : path.join(fixtures, "session", `${id}.json`)
}

function writeChunks(id, chunks) {
  const dir = path.join(fixtures, "replay", id)
  rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true })
  for (const { events, ...head } of chunks) {
    const text = `${JSON.stringify(head).slice(0, -1)},"events":[\n${events.map((e) => JSON.stringify(e)).join(",\n")}\n]}\n`
    writeFileSync(path.join(dir, `${head.chunk}.json`), text)
  }
  return dir
}

function updateSample(walk, recorded, chunks, srv) {
  const file = samplePath(walk.id), sample = readJson(file)
  const firstMs = chunks[0].start_ms
  const startMs = sample.replay.start_ms > firstMs ? sample.replay.start_ms : firstMs
  const metas = chunks.flatMap((c) => c.events).filter((e) => e.type === RRWEB.meta && e.timestamp - recorded.t0 <= startMs)
  sample.replay = { ...sample.replay, start_ms: startMs, start_url: metas.at(-1).data.href, epoch_ms: recorded.t0,
    chunks: chunks.map(({ start_ms, end_ms }) => ({ start_ms, end_ms })), missing: null }
  sample.actions = recorded.actions
  sample.server = { ...sample.server, pages: srv.map((row) => serverPage(row, recorded.t0)) }
  writeFileSync(file, JSON.stringify(sample, null, 2) + "\n")
  return file
}

/** Fails when a written file holds something that must never be in a sample. */
function privacyCheck(files, cake) {
  const banned = [...TYPED, cake.home, `:${cake.port}`, `:${cake.shopPort}`, cake.siteKey()]
  for (const file of files) {
    const hit = forbidden(readFileSync(file, "utf8"), banned)
    if (hit) throw new Error(`${path.relative(web, file)} holds "${hit}": not written to a sample`)
  }
}

const cake = await startCake()
const browser = await launch()
try {
  for (const walk of WALKS) {
    const recorded = await record(cake, browser, walk)
    if (!recorded.id) throw new Error(`${walk.id}: no session arrived`)
    const { events: raw, srv } = cake.read(recorded.id)
    const rows = raw.filter(([ts]) => ts - recorded.t0 <= walk.duration_ms)
    const pages = pageViews(rows, walk.id), expected = readJson(samplePath(walk.id)).session.pages
    if (pages !== expected) throw new Error(`${walk.id}: ${pages} page views recorded, the sample lists ${expected}`)
    const events = rows.map(([, text]) => JSON.parse(clean(text, cake)))
    const chunks = chunksOf(events, recorded.t0)
    const dir = writeChunks(walk.id, chunks)
    const sample = updateSample(walk, recorded, chunks, srv)
    privacyCheck([sample, ...chunks.map((c) => path.join(dir, `${c.chunk}.json`))], cake)
    console.log(`${walk.id}: ${events.length} events of ${pages} page views in ${chunks.length} chunks, ${srv.length} server-half pages, ${recorded.actions.length} actions`)
  }
} finally {
  await browser.close()
  await cake.stop()
}
