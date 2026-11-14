"use strict"
/*
 * node-crypto.js — HMAC-SHA256 and random token ids with Node's crypto module. Synchronous, so the Node mounting adds the
 * token without waiting for anything. Only express.js loads this file: the edge runtime has no node:crypto.
 * Step S4.1.
 */
const { createHmac, createSecretKey, randomBytes } = require("node:crypto")
const { encodeBase64Url } = require("./token")

const HMAC_HASH = "sha256" // protocol: the token's MAC

// mac(text) → Uint8Array, now.
function nodeMac(secret) {
  const key = createSecretKey(secret)
  return (text) => createHmac(HMAC_HASH, key).update(text, "utf8").digest()
}

function nodeRandomId(byteCount) {
  return encodeBase64Url(randomBytes(byteCount))
}

module.exports = { nodeMac, nodeRandomId }
