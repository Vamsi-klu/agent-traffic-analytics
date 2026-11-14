"use strict"
/*
 * hono.js — the mounting for Hono, on Node, Bun, Deno or Cloudflare Workers:
 *
 *   import { cakeHono } from "@agentcake/edge/hono"
 *   app.use(cakeHono({ clientIp: (c) => c.req.header("cf-connecting-ip") }))
 *
 * The token is made before the handler runs and set on the handler's response after, so noStore sees the response's
 * type. Web Crypto only, so it runs wherever Hono does. The secret is the option, else the CAKE_SERVER_TIMING_SECRET
 * binding (c.env, as Workers hand bindings over), else the environment variable. On Node (@hono/node-server) the raw
 * request in c.env.incoming keeps the header order. As in botscent's Hono adapter (src/adapters/hono.ts, MIT, 7f948003),
 * Hono's c.res setter copies the old response's headers onto a new one, so c.res is cleared before a copy is set.
 * Step S4.1.
 */
const { createCakeEdge } = require("./index")
const { addressOf } = require("./lib/request")
const { isHtml, responseWith } = require("./lib/timing")

/*
 * `options`: secret, clientIp(c), botscent, noStore, verdictWaitMs, maxHeaderNames, cut, skipExtensions, and now /
 * randomId / warn for tests.
 */
function cakeHono(options = {}) {
  const edge = createCakeEdge(options)
  const { headers: names, fixed } = edge.settings
  const middleware = async function cakeServerTiming(c, next) {
    let token = null
    try {
      const incoming = c.env && c.env.incoming
      token = await edge.token(c.req.raw, { ip: addressOf(options.clientIp, c), rawHeaders: incoming && incoming.rawHeaders, env: c.env })
    } catch {
      token = null // the server half must never break a page
    }
    await next()
    if (token === null || !c.res) return
    try {
      const noStore = edge.settings.no_store && isHtml(c.res.headers.get(names.content_type), fixed)
      const response = responseWith(c.res, token, edge.settings, noStore)
      if (response !== c.res) {
        c.res = undefined
        c.res = response
      }
    } catch {
      // The page goes out without the token rather than not at all.
    }
  }
  middleware.enabled = edge.enabled
  return middleware
}

module.exports = { cakeHono }
