// Tests for the fixture /api of the screenshot and dev servers (S5.1): the same routes, filters and errors as the
// contract, and every answer fits its schema. Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { createServer } from "node:http"
import path from "node:path"
import { after, before, test } from "node:test"
import { CONTRACT } from "./check-schemas.mjs"
import { LIBRARY, fixtureApi } from "./fixture-api.mjs"
import { loadSchemas, validate } from "./json-schema.mjs"

const schemas = loadSchemas(CONTRACT.schemaDir)
let server, base
before(async () => {
  const api = fixtureApi()
  server = createServer((req, res) => api(req, res, () => { res.statusCode = 418; res.end() }))
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve))
  base = `http://127.0.0.1:${server.address().port}`
})
after(() => server.close())

async function call(url, init) {
  const res = await fetch(base + url, init)
  return { status: res.status, body: res.headers.get("content-type")?.includes("json") ? await res.json() : null }
}
const fits = (body, file) => assert.deepEqual(validate(body, schemas.get(file), file, schemas), [])
const post = (body, type = "application/json") => call("/api/settings", { method: "POST", headers: { "content-type": type }, body: JSON.stringify(body) })
const ids = (body) => body.results.map((s) => s.id)

test("every GET endpoint answers its sample, and each fits its schema", async () => {
  for (const [url, file] of [["/api/overview", "overview"], ["/api/sessions", "sessions"], ["/api/session/7f3a-c1", "session"],
    ["/api/session/2b9e-c4", "session"], ["/api/session/7f3a-c1/replay?chunk=0", "replay"], ["/api/session/6e0f-13/replay?chunk=4", "replay"],
    ["/api/settings", "settings"], ["/api/setup", "setup"], ["/api/health", "health"], ["/api/register", "register"]]) {
    const { status, body } = await call(url)
    assert.equal(status, 200, url)
    fits(body, `${file}.schema.json`)
  }
})

test("the samples' AgentCake has registered, so every page shows at once (S5.8)", async () => {
  const { body } = await call("/api/register")
  assert.equal(body.registered, true)
})

test("the session list filters by verdict, split and agent like the real one", async () => {
  assert.deepEqual(ids((await call("/api/sessions?verdict=agent")).body), ["7f3a-c1", "a91e-07", "19fc-90", "b06c-41", "f8a2-6d", "6e0f-13"])
  assert.deepEqual(ids((await call("/api/sessions?turns=human_agent")).body), ["7f3a-c1", "f8a2-6d"])
  assert.deepEqual(ids((await call("/api/sessions?verdict=agent&turns=agent_only&agent=Grok%20Bot")).body), ["b06c-41"])
  assert.deepEqual(ids((await call("/api/sessions?verdict=bot")).body), ["c2d0-5b", "d3e1-8a"])
  assert.deepEqual(ids((await call("/api/sessions?agent=Meta%20Muse")).body), ["a91e-07"])
})

test("the next page of the sample list is empty and last", async () => {
  const { body } = await call("/api/sessions?cursor=sample-page-2")
  assert.deepEqual([body.results, body.next], [[], null])
})

test("each sample session answers its own replay chunks, in order (S5.4)", async () => {
  for (const id of ["7f3a-c1", "6e0f-13", "19fc-90"]) {
    const { body: detail } = await call(`/api/session/${id}`)
    for (const [n, span] of detail.replay.chunks.entries()) {
      const { status, body } = await call(`/api/session/${id}/replay?chunk=${n}`)
      assert.equal(status, 200, `${id} chunk ${n}`)
      assert.deepEqual([body.chunk, body.start_ms, body.end_ms], [n, span.start_ms, span.end_ms], `${id} chunk ${n}`)
    }
  }
})

test("unknown sessions, chunks, filters and addresses get an error body", async () => {
  for (const [url, status] of [["/api/session/0000-00", 404], ["/api/session/7f3a-c1/replay?chunk=99", 404], ["/api/session/7f3a-c1/replay?chunk=x", 404],
    ["/api/session/2b9e-c4/replay?chunk=0", 404], ["/api/session/..%2Fsession/replay?chunk=0", 404], ["/api/sessions?verdict=robots", 400], ["/api/nothing", 404]]) {
    const answer = await call(url)
    assert.equal(answer.status, status, url)
    fits(answer.body, "error.schema.json")
  }
})

test("POST /api/settings changes only the given fields and keeps them", async () => {
  const saved = await post({ retention_days: 90, hook_dom: true, site_domain: "https://shop.example.org/" })
  assert.equal(saved.status, 200)
  fits(saved.body, "settings.schema.json")
  assert.deepEqual([saved.body.retention_days, saved.body.hook_dom, saved.body.site_domain], [90, true, "shop.example.org"])
  assert.equal((await call("/api/settings")).body.retention_days, 90)
})

test("POST /api/settings refuses what cake would refuse", async () => {
  for (const [body, type] of [[{ retention_days: 7 }, "application/json"], [{ budget_mb: 3 }, "application/json"], [{ theme: "dark" }, "application/json"],
    [{ auto_free: "yes" }, "application/json"], [{ auto_free: false }, "text/plain"], [{ layers: { verify: false } }, "application/json"]]) {
    const answer = await post(body, type)
    assert.equal(answer.status, 400, JSON.stringify(body) + " " + type)
    fits(answer.body, "error.schema.json")
  }
})

test("anything outside /api goes on to the next handler", async () => {
  assert.equal((await call("/index.html")).status, 418)
})

test("the library set answers cake's own answers on the fixed test library, and the plain samples for the rest", async () => {
  const api = fixtureApi({ set: LIBRARY })
  const library = createServer((req, res) => api(req, res, () => { res.statusCode = 418; res.end() }))
  await new Promise((resolve) => library.listen(0, "127.0.0.1", resolve))
  const get = async (url) => (await fetch(`http://127.0.0.1:${library.address().port}${url}`)).json()
  try {
    for (const [endpoint, file] of [["overview", "overview"], ["sessions", "sessions"], ["setup", "setup"]]) {
      const body = await get(`/api/${endpoint}`)
      fits(body, `${file}.schema.json`)
      assert.notDeepEqual(body, (await call(`/api/${endpoint}`)).body, `${endpoint}: not the plain sample`)
    }
    assert.deepEqual(await get("/api/settings"), JSON.parse(readFileSync(path.join(CONTRACT.fixtureDir, "settings.json"), "utf8")))
  } finally { library.close() }
})
