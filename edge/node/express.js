"use strict"
/*
 * express.js — the mounting for Express, Connect and plain node:http, and so for a Next.js custom server: a middleware
 * (req, res, next) that puts cake's entry on the response to each page request.
 *
 *   const { cakeExpress } = require("@agentcake/edge/express")
 *   app.use(cakeExpress({ clientIp: (req) => req.ip }))      // the secret: CAKE_SERVER_TIMING_SECRET
 *
 * Node's crypto signs synchronously, so without botscent the middleware waits for nothing. The entry is written when the
 * response's head is (a writeHead hook, the way the on-headers package and botscent's Express adapter work), so a
 * handler that sets its own Server-Timing later, with setHeader or writeHead, keeps its entries and cake's, and noStore
 * can see the type the handler chose. The hook is adapted from botscent (https://github.com/nalinbhardwaj/botscent,
 * src/adapters/express.ts, commit 7f948003, Copyright (c) 2026 Nalin Bhardwaj, MIT License).
 */
const { settingsFrom, resolveSecret, secretBytes, startupWarnings, warnOnce } = require("./lib/settings")
const { viewOf, botscentRequestOf, addressOf } = require("./lib/request")
const { isPageRequest } = require("./lib/facts")
const { mintWith } = require("./lib/mint")
const { nodeMac, nodeRandomId } = require("./lib/node-crypto")
const { NO_VERDICT, verdictSource } = require("./lib/verdict")
const { withCakeEntry, isHtml } = require("./lib/timing")

function passThrough() {
  const middleware = (req, res, next) => next()
  middleware.enabled = false
  return middleware
}

// The request's view when it is a page whose response has not started, else null.
function pageView(req, res, settings) {
  try {
    if (res.headersSent) return null
    const view = viewOf(req)
    return isPageRequest(view, settings) ? view : null
  } catch {
    return null
  }
}

// The values of one header in writeHead's headers argument: an object, or a flat [name, value, ...] list.
function valuesIn(head, name) {
  const pairs = Array.isArray(head) ? head.flatMap((item, i) => (i % 2 ? [] : [[item, head[i + 1]]])) : Object.entries(head || {})
  return pairs.filter(([key]) => String(key).toLowerCase() === name).flatMap(([, value]) => [].concat(value).map(String))
}

function withoutHeader(head, name) {
  if (Array.isArray(head)) return head.filter((item, i, all) => String(all[i - (i % 2)]).toLowerCase() !== name)
  if (!head) return head
  return Object.fromEntries(Object.entries(head).filter(([key]) => String(key).toLowerCase() !== name))
}

/*
 * The head as it goes out: Server-Timing from setHeader and from writeHead's argument merged, with cake's entry; for
 * HTML under noStore, Cache-Control private, no-store. Both are set on the response and taken out of the argument, since
 * Node lets the argument win over setHeader.
 */
function headWithEntry(res, head, token, settings) {
  const { headers: names, fixed } = settings
  const fromResponse = [].concat(res.getHeader(names.server_timing) ?? []).map(String)
  const existing = [...fromResponse, ...valuesIn(head, names.server_timing)].join(", ")
  let out = withoutHeader(head, names.server_timing)
  res.setHeader(names.server_timing, withCakeEntry(existing, token, fixed))
  if (settings.no_store && isHtml(valuesIn(head, names.content_type)[0] ?? res.getHeader(names.content_type), fixed)) {
    out = withoutHeader(out, names.cache_control)
    res.setHeader(names.cache_control, fixed.no_store_value)
  }
  return out
}

function attach(res, token, settings) {
  const writeHead = res.writeHead
  let written = false
  res.writeHead = function writeHeadWithCakeEntry(statusCode, ...rest) {
    if (!written) {
      written = true
      const at = typeof rest[0] === "string" ? 1 : 0 // writeHead(status, [statusMessage], [headers])
      try {
        rest[at] = headWithEntry(this, rest[at], token, settings)
      } catch {
        // The server half must never break a page: the head goes out as the handler wrote it.
      }
    }
    return writeHead.call(this, statusCode, ...rest)
  }
}

/*
 * `options`: secret (default: the CAKE_SERVER_TIMING_SECRET environment variable), clientIp(req) (the visitor's address
 * as the app knows it, e.g. req.ip under Express's trust proxy; without it the token has no network key), botscent (its
 * botscent/server module, or the promise import() returns), noStore, verdictWaitMs, maxHeaderNames, cut, skipExtensions,
 * and now / randomId / warn for tests. With no secret, or one shorter than 32 bytes, it passes every request through.
 */
function cakeExpress(options = {}) {
  const settings = settingsFrom(options)
  const warn = warnOnce(options)
  const given = resolveSecret(options.secret, settings)
  startupWarnings(settings, given).forEach(warn)
  const secret = secretBytes(given, settings.fixed)
  if (!secret) return passThrough()
  const mac = nodeMac(secret)
  const now = typeof options.now === "function" ? options.now : Date.now
  const randomId = typeof options.randomId === "function" ? options.randomId : () => nodeRandomId(settings.fixed.token_id_bytes)
  const verdicts = verdictSource(options.botscent)

  const middleware = function cakeServerTiming(req, res, next) {
    const view = pageView(req, res, settings)
    if (!view) return next()
    const meta = { id: randomId(), t: now(), ip: addressOf(options.clientIp, req) }
    const finish = ({ verdict, version }) => {
      try {
        attach(res, mintWith(mac, view, { ...meta, verdict, version }, settings), settings)
      } catch {
        // The server half must never break a page: a token that cannot be made is not sent.
      }
      next()
    }
    if (!verdicts) return finish(NO_VERDICT)
    verdicts.read(botscentRequestOf(req), settings.verdict_wait_ms).then(finish, () => finish(NO_VERDICT))
  }
  middleware.enabled = true
  return middleware
}

// The token for `request` with everything that varies given, signed with Node's crypto (see index.js mintToken).
function mintTokenSync(secret, request, { nowMs, id, ip = null, verdict = null, version = null, rawHeaders, ...options } = {}) {
  const settings = settingsFrom(options)
  const bytes = secretBytes(secret, settings.fixed)
  if (!bytes) return null
  const view = viewOf(request, rawHeaders)
  return isPageRequest(view, settings) ? mintWith(nodeMac(bytes), view, { id, t: nowMs, ip, verdict, version }, settings) : null
}

module.exports = { cakeExpress, cakeNode: cakeExpress, mintTokenSync }
