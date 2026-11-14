"use strict"
/*
 * hono.test.js — the Hono mounting, on a context shaped like Hono's (c.req.raw, c.res, c.env): the entry goes on the
 * response after the handler has made it, so noStore can look at its type; on Node the raw request keeps the header
 * order; on Workers the secret can come from the bindings.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const { fixed, options: defaults } = require("../defaults.json")
const { cakeHono } = require("../hono")
const { verifyToken } = require("..")
const { SECRET, NOW, CLIENT_IP, CHROME_PAGE, withHeaders, fetchRequest, tokenIn } = require("./helpers")

const options = { secret: SECRET, now: () => NOW, randomId: () => "id-1", clientIp: () => CLIENT_IP, warn: () => {} }
const html = () => new Response("<p>shop</p>", { headers: { "content-type": "text/html; charset=utf-8" } })

// Runs the middleware the way Hono does: the handler sets c.res inside next().
async function run(middleware, request, { env, respond = html } = {}) {
  const c = { req: { raw: request }, env, res: undefined }
  let handled = false
  await middleware(c, async () => {
    handled = true
    c.res = respond()
  })
  return { response: c.res, handled }
}

const tokenOf = (response) => tokenIn(response.headers.get("server-timing"))

test("after the handler, its response carries the cake entry, and the token verifies", async () => {
  const { response, handled } = await run(cakeHono(options), fetchRequest("/"))
  assert.ok(handled)
  assert.equal(await response.text(), "<p>shop</p>")
  const { result, payload } = await verifyToken(SECRET, tokenOf(response), { nowMs: NOW })
  assert.equal(result, "ok")
  assert.deepEqual(payload.sf, { s: "none", m: "navigate", d: "document", u: "?1" })
  assert.equal(payload.hn, null, "a Fetch Request does not keep the order of its headers")
})

test("on Node, Hono's raw request (c.env.incoming) keeps the header order", async () => {
  const incoming = { rawHeaders: CHROME_PAGE.flatMap(([name, value]) => [name, value]) }
  const { response } = await run(cakeHono(options), fetchRequest("/"), { env: { incoming } })
  const { payload } = await verifyToken(SECRET, tokenOf(response), { nowMs: NOW })
  assert.deepEqual(payload.hn.slice(0, 2), ["host", "connection"])
})

test("the secret can come from c.env, as Cloudflare Workers bindings hand it over", async () => {
  const { secret, ...rest } = options
  const env = { [defaults.secret_env]: secret }
  const { response } = await run(cakeHono(rest), fetchRequest("/"), { env })
  assert.equal((await verifyToken(SECRET, tokenOf(response), { nowMs: NOW })).result, "ok")
  const { response: none } = await run(cakeHono(rest), fetchRequest("/"), { env: {} })
  assert.equal(none.headers.get("server-timing"), null, "and without one anywhere, nothing is sent")
})

test("noStore makes HTML private and unstored, and leaves every other type alone", async () => {
  const cake = cakeHono({ ...options, noStore: true })
  const { response } = await run(cake, fetchRequest("/"))
  assert.equal(response.headers.get("cache-control"), fixed.no_store_value)
  const json = () => new Response("{}", { headers: { "content-type": "application/json", "cache-control": "max-age=60" } })
  const { response: data } = await run(cake, fetchRequest("/data"), { respond: json })
  assert.equal(data.headers.get("cache-control"), "max-age=60")
})

test("a response whose headers cannot change is replaced by a copy that carries the entry", async () => {
  const redirect = () => Response.redirect("https://shop.example/next", 302)
  const { response } = await run(cakeHono(options), fetchRequest("/"), { respond: redirect })
  assert.equal(response.status, 302)
  assert.ok(tokenOf(response))
})

test("anything but a page: the handler runs and nothing is added", async () => {
  const script = fetchRequest("/app", withHeaders(CHROME_PAGE, { "sec-fetch-dest": "script" }))
  const { response, handled } = await run(cakeHono(options), script)
  assert.ok(handled)
  assert.equal(response.headers.get("server-timing"), null)
})
