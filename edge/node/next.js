"use strict"
/*
 * next.js — the mounting for Next.js middleware (middleware.ts; proxy.ts from Next.js 16), on the edge runtime or on
 * Node. It adds cake's entry to the response the middleware returns:
 *
 *   import { NextResponse } from "next/server"
 *   import { cakeNext } from "@agentcake/edge/next"
 *   const cake = cakeNext()                                   // the secret: CAKE_SERVER_TIMING_SECRET
 *   export default async function middleware(request) {
 *     return cake(request, NextResponse.next())
 *   }
 *
 * This package depends on nothing, Next.js included, so the response comes from the site: NextResponse.next(), or what
 * its own middleware returns. Web Crypto only, since the edge runtime has no Node crypto. Next.js hands middleware a
 * Headers object, which does not keep the request's header order, so the token's header names are null here. The
 * middleware runs before the page's own response exists, so noStore marks the response of every page navigation. As in
 * botscent's Next.js adapter (src/adapters/next.ts, MIT, 7f948003), a response whose headers cannot change is copied,
 * never thrown on.
 */
const { createCakeEdge } = require("./index")
const { message, warnOnce } = require("./lib/settings")
const { addressOf } = require("./lib/request")
const { responseWith } = require("./lib/timing")

/*
 * `options`: secret, clientIp(request) (the visitor's address as the platform gives it, e.g. the x-real-ip header your
 * host sets; without it the token has no network key), botscent, noStore, verdictWaitMs, maxHeaderNames, cut,
 * skipExtensions, and now / randomId / warn for tests. cake(request, response) resolves to the response to return.
 */
function cakeNext(options = {}) {
  const edge = createCakeEdge(options)
  const warn = warnOnce(options)
  const cake = async function cakeServerTiming(request, response) {
    if (!response) {
      warn(message(edge.settings, "no_response"))
      return response
    }
    try {
      const token = await edge.token(request, { ip: addressOf(options.clientIp, request) })
      return token === null ? response : responseWith(response, token, edge.settings, edge.settings.no_store)
    } catch {
      return response // the server half must never break a page
    }
  }
  cake.enabled = edge.enabled
  return cake
}

module.exports = { cakeNext }
