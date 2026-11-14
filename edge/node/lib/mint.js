"use strict"
/*
 * mint.js — a token from a request's facts, its id and time, the network key and botscent's verdict, with a MAC that is
 * computed at once (Node's crypto) or later (Web Crypto). The payload's keys are always in one order, which is part of
 * the format: v, id, t, p, sf, sp, md, al, ch, ua, hn, sg, ik, bs, bsv. Also signing a payload as it is and verifying a
 * token, for tests and for anyone checking a token by hand; cake verifies with its own copy (agentcake/edge_token.py).
 *
 */
const { requestFacts, verdictFields, versionOf } = require("./facts")
const { networkText, networkKeyOf } = require("./netkey")
const { BAD, bodyOf, signedTextOf, assemble, partsOf, conclude } = require("./token")

function payloadOf(view, { id, t, ik, verdict, version }, settings) {
  const fixed = settings.fixed
  return { v: fixed.payload_version, id, t, ...requestFacts(view, settings), ik, bs: verdictFields(verdict, fixed), bsv: versionOf(version, fixed) }
}

// mac(text) returns the MAC's bytes now. `meta` is { id, t, ip, verdict, version }.
function mintWith(mac, view, meta, settings) {
  const fixed = settings.fixed
  const text = networkText(meta.ip, meta.t, fixed)
  const ik = text === null ? null : networkKeyOf(mac(text), fixed)
  const body = bodyOf(payloadOf(view, { ...meta, ik }, settings))
  return assemble(body, mac(signedTextOf(body, fixed)), fixed)
}

// The same, with a mac(text) that returns a promise of the bytes.
async function mintWithAsync(mac, view, meta, settings) {
  const fixed = settings.fixed
  const text = networkText(meta.ip, meta.t, fixed)
  const ik = text === null ? null : networkKeyOf(await mac(text), fixed)
  const body = bodyOf(payloadOf(view, { ...meta, ik }, settings))
  return assemble(body, await mac(signedTextOf(body, fixed)), fixed)
}

async function signWithAsync(mac, payload, fixed) {
  const body = bodyOf(payload)
  return assemble(body, await mac(signedTextOf(body, fixed)), fixed)
}

async function verifyWithAsync(mac, token, nowMs, window, fixed) {
  const parts = partsOf(token, fixed)
  return parts ? conclude(parts, await mac(parts.signedText), nowMs, window, fixed) : BAD
}

module.exports = { mintWith, mintWithAsync, signWithAsync, verifyWithAsync }
