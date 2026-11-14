"use strict"
/*
 * token.js — the server-half token: `c1.<base64url(JSON payload)>.<base64url(HMAC-SHA256(secret, "c1." + body))>`.
 *
 * Only base64url characters and dots, so it sits in a Server-Timing desc quoted string as it is. The MAC is computed by
 * the caller (Node's crypto in express.js, Web Crypto everywhere else); this file lays the token out and reads it back,
 * so both paths share one format. Reading is strict, the way cake's verifier reads: one prefix, three parts, base64url
 * without padding, the MAC compared in its one spelling (spare bits zero), and a payload that is a JSON object with this
 * version, an id and a time in milliseconds. The format is the one tartini.ai's cake-server-timing.js and cake 0.3.3 used
 * (toast_mvp branch cake-tartini, 01eafdb7); the shared vectors (tests/vectors/edge_token.json) pin it.
 */
const BASE64URL = /^[A-Za-z0-9_-]+$/
const encoder = new TextEncoder()
const decoder = new TextDecoder("utf-8", { fatal: true })
// Node's Buffer when there is one: btoa over a character-by-character string costs a token most of its time on Node. The
// edge runtime has no Buffer and uses btoa; both write the same text, which the shared vectors check on both paths.
const NodeBuffer = typeof Buffer === "function" ? Buffer : null

function encodeBase64Url(bytes) {
  if (NodeBuffer) return NodeBuffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength).toString("base64url")
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

// The bytes of a base64url text in its one spelling (no padding, spare bits zero), or null.
function decodeBase64Url(text) {
  if (typeof text !== "string" || !BASE64URL.test(text)) return null
  let binary
  try {
    binary = atob(text.replace(/-/g, "+").replace(/_/g, "/"))
  } catch {
    return null
  }
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  return encodeBase64Url(bytes) === text ? bytes : null
}

// The token's middle part. JSON.stringify keeps the payload's key order, which is part of the format.
function bodyOf(payload) {
  const json = JSON.stringify(payload)
  return NodeBuffer ? NodeBuffer.from(json, "utf8").toString("base64url") : encodeBase64Url(encoder.encode(json))
}

// What the MAC covers.
function signedTextOf(body, fixed) {
  return `${fixed.token_prefix}.${body}`
}

function assemble(body, mac, fixed) {
  return `${signedTextOf(body, fixed)}.${encodeBase64Url(mac)}`
}

// The parts of something shaped like a token, { signedText, body, mac }, or null.
function partsOf(token, fixed) {
  if (typeof token !== "string") return null
  const parts = token.split(".")
  if (parts.length !== 3 || parts[0] !== fixed.token_prefix || !BASE64URL.test(parts[1]) || !BASE64URL.test(parts[2])) return null
  return { signedText: `${parts[0]}.${parts[1]}`, body: parts[1], mac: parts[2] }
}

// Two texts compared in a time that does not depend on where they first differ.
function sameText(a, b) {
  if (a.length !== b.length) return false
  let difference = 0
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return difference === 0
}

function payloadFromBody(body, fixed) {
  const bytes = decodeBase64Url(body)
  if (!bytes) return null
  let payload
  try {
    payload = JSON.parse(decoder.decode(bytes))
  } catch {
    return null
  }
  const isObject = payload !== null && typeof payload === "object" && !Array.isArray(payload)
  if (!isObject || payload.v !== fixed.payload_version) return null
  if (typeof payload.id !== "string" || payload.id === "" || !Number.isSafeInteger(payload.t)) return null
  return payload
}

const BAD = Object.freeze({ result: "bad" })

/*
 * What a verifier concludes from a token's parts and the MAC it computed over parts.signedText: { result: "ok",
 * payload }, { result: "stale", payload } when the time is outside the window, or { result: "bad" }. The window is
 * cake's: `maxAgeMs` after the token's time, `maxFutureMs` before it (a server clock a little ahead).
 */
function conclude(parts, mac, nowMs, window, fixed) {
  if (!parts || !sameText(encodeBase64Url(mac), parts.mac)) return BAD
  const payload = payloadFromBody(parts.body, fixed)
  if (!payload) return BAD
  const maxAgeMs = window.maxAgeMs !== undefined ? window.maxAgeMs : fixed.verify_max_age_ms
  const maxFutureMs = window.maxFutureMs !== undefined ? window.maxFutureMs : fixed.verify_max_future_ms
  const stale = payload.t > nowMs + maxFutureMs || nowMs - payload.t > maxAgeMs
  return { result: stale ? "stale" : "ok", payload }
}

module.exports = { BAD, encodeBase64Url, decodeBase64Url, bodyOf, signedTextOf, assemble, partsOf, conclude }
