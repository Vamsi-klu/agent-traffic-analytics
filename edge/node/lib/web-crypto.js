"use strict"
/*
 * web-crypto.js — HMAC-SHA256 and random token ids with Web Crypto (crypto.subtle, crypto.getRandomValues): the path for
 * Next.js middleware (the edge runtime has no Node crypto), Hono on any runtime, Workers, Deno and Bun. No Node API.
 * Step S4.1.
 */
const { encodeBase64Url } = require("./token")

const encoder = new TextEncoder()
const HMAC = { name: "HMAC", hash: "SHA-256" } // protocol: the token's MAC

// mac(text) → Promise<Uint8Array>, with the key imported once.
function webMac(secret) {
  const key = crypto.subtle.importKey("raw", secret, HMAC, false, ["sign"])
  // A key that cannot be imported fails each mac() call; this keeps it from also being reported as unhandled.
  key.catch(() => {})
  return async (text) => new Uint8Array(await crypto.subtle.sign(HMAC.name, await key, encoder.encode(text)))
}

function webRandomId(byteCount) {
  return encodeBase64Url(crypto.getRandomValues(new Uint8Array(byteCount)))
}

module.exports = { webMac, webRandomId }
