"use strict"
/*
 * next.test.js — the Next.js mounting (middleware.ts, or proxy.ts from Next.js 16). It uses Web Crypto only, so it runs
 * in the edge runtime as well as on Node. The edge runtime is simulated the way Next.js runs middleware: in a separate
 * V8 context that has the Web APIs and none of Node's. next.js and everything it loads must run there unchanged.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { fixed } = require("../defaults.json")
const { cakeNext } = require("../next")
const { mintTokenSync } = require("../express")
const { verifyToken } = require("..")
const { SECRET, NOW, CLIENT_IP, CHROME_PAGE, withHeaders, fetchRequest, tokenIn } = require("./helpers")

const options = { secret: SECRET, now: () => NOW, randomId: () => "id-1", clientIp: () => CLIENT_IP, warn: () => {} }
// What NextResponse.next() is: a Response whose x-middleware-next header tells Next.js to go on to the route.
const nextResponse = () => new Response(null, { headers: { "x-middleware-next": "1" } })

test("the Next.js middleware adds the cake entry to the response it is given", async () => {
  const response = await cakeNext(options)(fetchRequest("/products/cake"), nextResponse())
  assert.equal(response.headers.get("x-middleware-next"), "1", "the response it was given, carried on")
  const { result, payload } = await verifyToken(SECRET, tokenIn(response.headers.get("server-timing")), { nowMs: NOW })
  assert.equal(result, "ok")
  assert.equal(payload.p, "/products/cake")
  assert.equal(payload.hn, null, "Next.js hands over Headers, which do not keep their order")
})

test("the Web Crypto path makes the token the Node path makes for the same request, clock and id", async () => {
  const response = await cakeNext(options)(fetchRequest("/"), nextResponse())
  const node = mintTokenSync(SECRET, fetchRequest("/"), { nowMs: NOW, id: "id-1", ip: CLIENT_IP })
  assert.equal(tokenIn(response.headers.get("server-timing")), node)
})

test("it runs in a context with only the edge runtime's globals: no Node module, no Buffer, no process", async () => {
  const edge = loadInEdgeRuntime(path.join(__dirname, "..", "next.js"))
  const response = await edge.cakeNext(options)(fetchRequest("/"), nextResponse())
  const token = tokenIn(response.headers.get("server-timing"))
  assert.equal((await verifyToken(SECRET, token, { nowMs: NOW })).result, "ok")
  assert.equal(token, mintTokenSync(SECRET, fetchRequest("/"), { nowMs: NOW, id: "id-1", ip: CLIENT_IP }), "the same token")
  const random = await edge.cakeNext({ ...options, randomId: undefined })(fetchRequest("/"), nextResponse())
  assert.match(tokenIn(random.headers.get("server-timing")), /^c1\./, "and token ids from Web Crypto's random values")
  assert.throws(() => loadInEdgeRuntime(path.join(__dirname, "..", "express.js")), /cannot load "node:crypto"/,
    "the sandbox does refuse Node modules: the Express mounting cannot load there")
})

test("a response whose headers cannot change is copied, never thrown on", async () => {
  const redirect = Response.redirect("https://shop.example/next", 307)
  assert.throws(() => redirect.headers.set("x-probe", "1"), "a redirect's headers are immutable")
  const response = await cakeNext(options)(fetchRequest("/"), redirect)
  assert.notEqual(response, redirect)
  assert.equal(response.status, 307)
  assert.equal(response.headers.get("location"), "https://shop.example/next")
  assert.ok(tokenIn(response.headers.get("server-timing")))
})

test("anything but a page, no secret, or no response to add to: the response passes through untouched", async () => {
  const script = fetchRequest("/app.js", withHeaders(CHROME_PAGE, { "sec-fetch-dest": "script" }))
  const given = nextResponse()
  assert.equal(await cakeNext(options)(script, given), given)
  assert.equal((await cakeNext(options)(script, nextResponse())).headers.get("server-timing"), null)
  const off = cakeNext({ ...options, secret: undefined })
  assert.equal(off.enabled, false)
  assert.equal((await off(fetchRequest("/"), nextResponse())).headers.get("server-timing"), null)
  const warnings = []
  const forgetful = cakeNext({ ...options, warn: (line) => warnings.push(line) })
  assert.equal(await forgetful(fetchRequest("/")), undefined, "no response given: Next.js goes on as if none was returned")
  await forgetful(fetchRequest("/"))
  assert.equal(warnings.length, 1, "and says so once")
})

test("noStore: a page navigation's response is made private and unstored", async () => {
  const response = await cakeNext({ ...options, noStore: true })(fetchRequest("/"), nextResponse())
  assert.equal(response.headers.get("cache-control"), fixed.no_store_value)
  const plain = await cakeNext(options)(fetchRequest("/"), nextResponse())
  assert.equal(plain.headers.get("cache-control"), null, "off by default")
})

/*
 * Next.js runs middleware in a V8 context with the Web APIs (Request, Response, Headers, URL, TextEncoder, crypto.subtle,
 * atob, btoa, timers) and none of Node's. This loads a CommonJS file, and the files it requires, into such a context;
 * requiring anything but a file of this package fails, the way a Node module fails at the edge.
 */
function loadInEdgeRuntime(entry) {
  const context = vm.createContext({
    Request, Response, Headers, URL, URLSearchParams, TextEncoder, TextDecoder, crypto: globalThis.crypto,
    atob, btoa, setTimeout, clearTimeout, queueMicrotask, structuredClone, console,
  })
  const cache = new Map()
  const load = (file) => {
    if (cache.has(file)) return cache.get(file).exports
    const module = { exports: {} }
    cache.set(file, module)
    if (file.endsWith(".json")) {
      module.exports = JSON.parse(fs.readFileSync(file, "utf8"))
      return module.exports
    }
    const source = fs.readFileSync(file, "utf8")
    const wrapper = vm.runInContext(`(function (exports, require, module) {\n${source}\n})`, context, { filename: file })
    const requireHere = (specifier) => {
      if (!specifier.startsWith(".")) throw new Error(`the edge runtime cannot load "${specifier}"`)
      return load(resolveFile(path.resolve(path.dirname(file), specifier)))
    }
    wrapper(module.exports, requireHere, module)
    return module.exports
  }
  return load(entry)
}

function resolveFile(base) {
  for (const candidate of [base, `${base}.js`, `${base}.json`, path.join(base, "index.js")]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate
  }
  throw new Error(`cannot resolve ${base}`)
}
