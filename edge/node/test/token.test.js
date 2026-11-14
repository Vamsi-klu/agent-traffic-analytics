"use strict"
/*
 * token.test.js — the token's format: what it looks like, that it verifies, and what never verifies.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const { fixed } = require("../defaults.json")
const { mintToken, verifyToken, signPayload } = require("..")
const { SECRET, OTHER_SECRET, NOW, CLIENT_IP, plainRequest } = require("./helpers")

const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
const mint = (id = "id-1") => mintToken(SECRET, plainRequest("/"), { nowMs: NOW, id, ip: CLIENT_IP })
const resultOf = async (token, options = {}, secret = SECRET) => (await verifyToken(secret, token, { nowMs: NOW, ...options })).result

test("a token is c1, a base64url JSON payload and a base64url MAC, and it verifies", async () => {
  const token = await mint()
  assert.match(token, /^c1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/, "only base64url and dots: it sits in a quoted desc as it is")
  const { result, payload } = await verifyToken(SECRET, token, { nowMs: NOW })
  assert.equal(result, "ok")
  assert.equal(payload.v, fixed.payload_version)
  assert.equal(payload.id, "id-1")
  assert.equal(payload.t, NOW)
  assert.equal(payload.p, "/")
})

test("a changed byte, another secret, another prefix or a malformed token does not verify", async () => {
  const token = await mint()
  const [prefix, body, mac] = token.split(".")
  const flip = (text, at) => text.slice(0, at) + (text[at] === "A" ? "B" : "A") + text.slice(at + 1)
  for (const [why, candidate] of [
    ["a byte of the payload", `${prefix}.${flip(body, 10)}.${mac}`],
    ["a byte of the MAC", `${prefix}.${body}.${flip(mac, 5)}`],
    ["another prefix", `c2.${body}.${mac}`],
    ["two parts", `${prefix}.${body}`],
    ["four parts", `${token}.${mac}`],
    ["empty", ""],
    ["not a token", "garbage"],
  ]) {
    assert.equal(await resultOf(candidate), "bad", why)
  }
  assert.equal(await resultOf(token, {}, OTHER_SECRET), "bad", "another secret")
  const own = Buffer.from(JSON.stringify({ v: 1, id: "x", t: NOW })).toString("base64url")
  assert.equal(await resultOf(`${prefix}.${own}.${mac}`), "bad", "a payload of one's own under a real MAC")
})

test("older than the window or from the future is stale; the edges of the window are ok", async () => {
  const token = await mint()
  const maxAge = fixed.verify_max_age_ms
  const maxFuture = fixed.verify_max_future_ms
  assert.equal(await resultOf(token, { nowMs: NOW + maxAge }), "ok")
  assert.equal(await resultOf(token, { nowMs: NOW + maxAge + 1 }), "stale")
  assert.equal(await resultOf(token, { nowMs: NOW - maxFuture }), "ok")
  assert.equal(await resultOf(token, { nowMs: NOW - maxFuture - 1 }), "stale")
  assert.equal(await resultOf(token, { nowMs: NOW + 2, maxAgeMs: 1 }), "stale", "the window can be given")
})

test("the MAC is read in its one spelling: no padding, no standard-alphabet characters, no spare bits set", async () => {
  const token = await mint()
  const [prefix, body, mac] = token.split(".")
  assert.equal(await resultOf(`${prefix}.${body}.${mac}=`), "bad", "padding")
  // 32 bytes take 43 characters; the last one holds 4 bits of the MAC and 2 spare bits, which must be zero.
  const last = BASE64URL_ALPHABET.indexOf(mac[mac.length - 1])
  assert.equal(last % 4, 0, "the token's own spelling leaves the spare bits zero")
  const spare = `${mac.slice(0, -1)}${BASE64URL_ALPHABET[last + 1]}`
  assert.equal(await resultOf(`${prefix}.${body}.${spare}`), "bad", "the same bytes, spelled with a spare bit set")
  // A MAC holding "-" or "_", spelled with the standard alphabet's "+" and "/" instead.
  for (let n = 0; n < BASE64URL_ALPHABET.length; n++) {
    const other = await mint(`id-${n}`)
    const [, otherBody, otherMac] = other.split(".")
    if (!/[-_]/.test(otherMac)) continue
    const standard = otherMac.replace(/-/g, "+").replace(/_/g, "/")
    assert.equal(await resultOf(`${prefix}.${otherBody}.${standard}`), "bad", "the standard base64 alphabet")
    return
  }
  assert.fail("no MAC with - or _ among the ids tried")
})

test("a payload that is not an object with this version, an id and a time does not verify, even under a good MAC", async () => {
  for (const payload of [
    [1, 2],
    "a string",
    { v: 1, t: NOW },
    { v: 1, id: "", t: NOW },
    { v: 1, id: 7, t: NOW },
    { v: 1, id: "x" },
    { v: 1, id: "x", t: "now" },
    { v: 1, id: "x", t: NOW + 0.5 },
    { v: 2, id: "x", t: NOW },
    { id: "x", t: NOW },
  ]) {
    assert.equal(await resultOf(await signPayload(SECRET, payload)), "bad", JSON.stringify(payload))
  }
  assert.equal(await resultOf(await signPayload(SECRET, { v: 1, id: "x", t: NOW })), "ok", "the smallest payload that is one")
})

/*
 * The token tartini.ai's middleware makes and cake 0.3.3 checks (toast_mvp branch cake-tartini, cake-server-timing.test.js,
 * 01eafdb7): the format has not changed, so it still verifies.
 */
const TARTINI_SECRET = "k".repeat(48)
const TARTINI_TOKEN = "c1.eyJ2IjoxLCJpZCI6InZlY3Rvci0xIiwidCI6MTc5NDUwMjgwMDAwMCwicCI6Ii8iLCJicyI6eyJ0IjoiYWdlbnQiLCJhIjoiY2xhdWRlLWluLWNocm9tZSIsInIiOlsiZXh0ZW5zaW9uLW1hcmtlciJdfSwiaWsiOiIzMGZhOGNlMTFiN2E2YzJhIn0.ECFhiDnT7T0k45nKX4Vl4Z5ZaOaqBzKDynVqsUm_Y6Q"

test("the token of tartini.ai's middleware and cake 0.3.3 still verifies, and is made again byte for byte", async () => {
  const payload = { v: 1, id: "vector-1", t: NOW, p: "/", bs: { t: "agent", a: "claude-in-chrome", r: ["extension-marker"] }, ik: "30fa8ce11b7a6c2a" }
  assert.deepEqual(await verifyToken(TARTINI_SECRET, TARTINI_TOKEN, { nowMs: NOW }), { result: "ok", payload })
  assert.equal(await signPayload(TARTINI_SECRET, payload), TARTINI_TOKEN)
})
