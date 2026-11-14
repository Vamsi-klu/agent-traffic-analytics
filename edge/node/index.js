"use strict"
/*
 * AgentCake site middleware: the server half. On each page response it sets one signed token in Server-Timing,
 *
 *   Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"
 *
 * which cake.js reads from the page's navigation entry and hands to cake with the visit, so cake learns what only the
 * site's server saw about the page request. See README.md.
 *
 * Mount one of: ./express (Express, Connect, node:http, a Next.js custom server), ./next (Next.js middleware or proxy,
 * edge or Node runtime), ./hono (Hono on any runtime). This entry is what they share and what any other framework needs;
 * it uses Web Crypto and no Node API, so it loads at the edge too:
 *
 *   createCakeEdge(options).token(request, { ip, rawHeaders, env })   the token for a request, or null
 *   mintToken, signPayload, verifyToken, networkKey, ipPrefix, isPageRequest   the format, for tests and checks by hand
 *
 *
 */
const DEFAULTS = require("./defaults.json")
const { settingsFrom, resolveSecret, secretBytes, isShortSecret, message, startupWarnings, warnOnce } = require("./lib/settings")
const { viewOf, botscentRequestOf } = require("./lib/request")
const { isPageRequest: isPage } = require("./lib/facts")
const { ipPrefix: prefixOf, networkText, networkKeyOf } = require("./lib/netkey")
const { mintWithAsync, signWithAsync, verifyWithAsync } = require("./lib/mint")
const { encodeBase64Url } = require("./lib/token")
const { webMac, webRandomId } = require("./lib/web-crypto")
const { NO_VERDICT, verdictSource } = require("./lib/verdict")

const FIXED = DEFAULTS.fixed

/*
 * The core of a mounting. `options`: secret (default: the CAKE_SERVER_TIMING_SECRET variable, or a binding of that name
 * passed as `env`), botscent, noStore, verdictWaitMs, maxHeaderNames, cut, skipExtensions, and now / randomId / warn for
 * tests. token() never throws for a request it cannot read: such a request gets no token.
 */
function createCakeEdge(options = {}) {
  const settings = settingsFrom(options)
  const warn = warnOnce(options)
  const now = typeof options.now === "function" ? options.now : Date.now
  const randomId = typeof options.randomId === "function" ? options.randomId : () => webRandomId(FIXED.token_id_bytes)
  const verdicts = verdictSource(options.botscent)
  const startSecret = resolveSecret(options.secret, settings)
  startupWarnings(settings, startSecret).forEach(warn)
  // The MAC for the secret in use; Workers give it per request (env), always the same, so one is kept.
  let kept = { id: null, mac: null }
  const macFor = (env) => {
    const given = resolveSecret(options.secret, settings, env)
    const bytes = secretBytes(given, FIXED)
    if (!bytes) {
      if (isShortSecret(given, FIXED)) warn(message(settings, "short_secret", { min: FIXED.min_secret_bytes }))
      return null
    }
    const id = encodeBase64Url(bytes)
    if (kept.id !== id) kept = { id, mac: webMac(bytes) }
    return kept.mac
  }
  return {
    enabled: secretBytes(startSecret, FIXED) !== null,
    settings,
    async token(request, { ip = null, rawHeaders, env } = {}) {
      const mac = macFor(env)
      if (!mac) return null
      let view
      try {
        view = viewOf(request, rawHeaders)
        if (!isPage(view, settings)) return null
      } catch {
        return null // a request that cannot be read is not one the token could describe
      }
      const meta = { id: randomId(), t: now(), ip }
      const { verdict, version } = verdicts ? await verdicts.read(botscentRequestOf(request), settings.verdict_wait_ms) : NO_VERDICT
      return mintWithAsync(mac, view, { ...meta, verdict, version }, settings)
    },
  }
}

function macOf(secret) {
  const bytes = secretBytes(secret, FIXED)
  if (!bytes) throw new TypeError(`secret: a string or bytes, at least ${FIXED.min_secret_bytes} bytes long`)
  return webMac(bytes)
}

/*
 * The token for `request` with everything that varies given: { nowMs, id, ip, verdict, version, rawHeaders } plus any
 * option. null when the request gets none (not a page, or no usable secret). The shared vectors are made with this.
 */
async function mintToken(secret, request, { nowMs, id, ip = null, verdict = null, version = null, rawHeaders, ...options } = {}) {
  const settings = settingsFrom(options)
  const bytes = secretBytes(secret, FIXED)
  if (!bytes) return null
  const view = viewOf(request, rawHeaders)
  if (!isPage(view, settings)) return null
  return mintWithAsync(webMac(bytes), view, { id, t: nowMs, ip, verdict, version }, settings)
}

// A token for a payload exactly as given: for tests, and for checking how a verifier treats a payload.
function signPayload(secret, payload) {
  return signWithAsync(macOf(secret), payload, FIXED)
}

// { result: "ok" | "stale" | "bad", payload }, by the rules cake applies; the window defaults to cake's.
function verifyToken(secret, token, { nowMs = Date.now(), maxAgeMs, maxFutureMs } = {}) {
  return verifyWithAsync(macOf(secret), token, nowMs, { maxAgeMs, maxFutureMs }, FIXED)
}

async function networkKey(secret, ip, nowMs) {
  const mac = macOf(secret)
  const text = networkText(ip, nowMs, FIXED)
  return text === null ? null : networkKeyOf(await mac(text), FIXED)
}

function ipPrefix(ip) {
  return prefixOf(ip, FIXED)
}

function isPageRequest(request, options = {}) {
  return isPage(viewOf(request), settingsFrom(options))
}

module.exports = { createCakeEdge, mintToken, signPayload, verifyToken, networkKey, ipPrefix, isPageRequest, defaults: DEFAULTS }
