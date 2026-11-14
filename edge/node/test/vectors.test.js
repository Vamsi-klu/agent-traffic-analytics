"use strict"
/*
 * vectors.test.js — the shared test vectors (tests/vectors/edge_token.json), which cake's Python side checks too
 * (tests/test_edge_vectors.py). The same request, clock, id and address make the vector's token byte for byte on the
 * Node path, on the Web Crypto path and through a real HTTP server; each token verifies, or fails, as the file says.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const path = require("node:path")
const { mintToken, verifyToken, networkKey, ipPrefix } = require("..")
const { cakeExpress, mintTokenSync } = require("../express")
const { listen, send, tokenIn, payloadOf } = require("./helpers")

const VECTORS = require(path.join(__dirname, "..", "..", "..", "tests", "vectors", "edge_token.json"))
const secretOf = (name) => VECTORS.secrets[name]
const requestOf = ({ request }) => ({ method: request.method, path: request.path, headers: request.headers })
const extrasOf = (vector) => ({ nowMs: vector.now_ms, id: vector.id, ip: vector.client_ip, verdict: vector.verdict, version: vector.version })
// Node's HTTP client refuses control characters in a header value, so those vectors are checked as plain requests only.
const sendable = ({ request }) => request.headers.every(([, value]) => !/[\u0000-\u0008\u000a-\u001f\u007f]/.test(value))

test("the vectors hold pages and non-pages, every result a token can have, and both address families", () => {
  assert.ok(VECTORS.mint.some((vector) => vector.token) && VECTORS.mint.some((vector) => vector.token === null))
  assert.deepEqual([...new Set(VECTORS.verify.map((vector) => vector.result))].sort(), ["bad", "ok", "stale"])
  assert.ok(VECTORS.network_keys.some((vector) => /\./.test(vector.prefix)) && VECTORS.network_keys.some((vector) => /:/.test(vector.prefix)))
})

test("every mint vector: the Node path makes its token byte for byte, and the token holds its payload", () => {
  for (const vector of VECTORS.mint) {
    assert.equal(mintTokenSync(secretOf(vector.secret), requestOf(vector), extrasOf(vector)), vector.token, vector.name)
    if (vector.token) assert.deepEqual(payloadOf(vector.token), vector.payload, vector.name)
  }
})

test("every mint vector: the Web Crypto path makes the same token", async () => {
  for (const vector of VECTORS.mint) {
    assert.equal(await mintToken(secretOf(vector.secret), requestOf(vector), extrasOf(vector)), vector.token, vector.name)
  }
})

test("every mint vector sent to a real server through the Express middleware gets the same token", async () => {
  for (const vector of VECTORS.mint.filter(sendable)) {
    const botscent = vector.verdict ? { inspect: async () => vector.verdict, VERSION: vector.version } : undefined
    const middleware = cakeExpress({
      secret: secretOf(vector.secret), now: () => vector.now_ms, randomId: () => vector.id, clientIp: () => vector.client_ip, botscent, warn: () => {},
    })
    const server = await listen((req, res) => middleware(req, res, () => res.end("<p>ok</p>")))
    try {
      const res = await send(server.origin, vector.request.path, { method: vector.request.method, lines: vector.request.headers })
      assert.equal(tokenIn(res.headers["server-timing"]), vector.token, vector.name)
    } finally {
      await server.close()
    }
  }
})

test("every verify vector gives its result, and an accepted token its payload", async () => {
  const window = { maxAgeMs: VECTORS.rules.max_age_ms, maxFutureMs: VECTORS.rules.max_future_ms }
  for (const vector of VECTORS.verify) {
    const got = await verifyToken(secretOf(vector.secret), vector.token, { nowMs: vector.now_ms, ...window })
    assert.equal(got.result, vector.result, vector.name)
    if (vector.result === "ok") assert.deepEqual(got.payload, vector.payload, vector.name)
  }
})

test("every network key vector: the same prefix and the same key", async () => {
  for (const vector of VECTORS.network_keys) {
    assert.equal(ipPrefix(vector.ip), vector.prefix, vector.name)
    assert.equal(await networkKey(secretOf(vector.secret), vector.ip, vector.now_ms), vector.key, vector.name)
  }
})

test("no token in the vectors holds the client's address or its network prefix", () => {
  for (const vector of VECTORS.mint.filter((each) => each.token && each.client_ip)) {
    const text = JSON.stringify(payloadOf(vector.token))
    const network = ipPrefix(vector.client_ip).split("/")[0].replace(/(\.0|::)$/, "")
    assert.ok(!text.includes(vector.client_ip.trim()) && !text.includes(network), vector.name)
  }
})
