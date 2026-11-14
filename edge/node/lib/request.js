"use strict"
/*
 * request.js — one read-only view over the request shapes the middleware is given: { method, path, header(name), names }.
 *
 * Node's IncomingMessage (Express, Connect, node:http, a Next.js custom server), a Fetch Request (Next.js middleware,
 * Hono, Workers, Deno, Bun), or a plain { method, path, headers: [[name, value], ...] } (the shared test vectors).
 * Repeated header lines are joined with ", " and values trimmed, the way Fetch's Headers.get reads them, on every
 * runtime, so one request makes one token wherever it is read. `names` are the header names in the order the client
 * sent them, lower-cased; a Fetch Request does not keep that order (Headers iterates its names sorted), so its names are
 * null unless the runtime hands over the raw lines (Hono on Node does). The path is the request target's path as sent,
 * without the query: no URL parsing, since runtimes' URL parsers resolve odd paths differently (Node's leaves
 * "/a/.env/.." as it is and resolves "/a/b/..") and a browser sends its paths resolved already. One view over many
 * request shapes is botscent's idea (src/server/request.ts, MIT, 7f948003); this file is written for cake.
 */
const ABSOLUTE_FORM = /^[a-z][a-z0-9+.-]*:\/\/[^/?#]*/i // "https://shop.example" before the path of a full URL
const EDGE_WHITESPACE = /^[\t\n\r ]+|[\t\n\r ]+$/g

// [name, value, name, value, ...] (Node's rawHeaders) as [[name, value], ...].
function pairsOf(flat) {
  const pairs = []
  for (let i = 0; i + 1 < flat.length; i += 2) pairs.push([flat[i], flat[i + 1]])
  return pairs
}

// The path of a request target: "/a/b?q" (origin-form), "https://host/a/b?q" (absolute-form, and a Fetch Request's url).
function pathOf(target) {
  const text = String(target || "").replace(ABSOLUTE_FORM, "")
  const end = text.search(/[?#]/)
  return (end === -1 ? text : text.slice(0, end)) || "/"
}

function linesView(method, path, lines, ordered) {
  const values = new Map()
  const names = []
  for (const [rawName, rawValue] of lines) {
    const name = String(rawName).toLowerCase()
    const value = (Array.isArray(rawValue) ? rawValue.join(", ") : String(rawValue)).replace(EDGE_WHITESPACE, "")
    values.set(name, values.has(name) ? `${values.get(name)}, ${value}` : value)
    names.push(name)
  }
  return { method, path, header: (name) => (values.has(name) ? values.get(name) : null), names: ordered ? names : null }
}

function headersView(method, path, headers) {
  // Fetch's Headers throws on a name it finds invalid; such a header is simply not there.
  const header = (name) => {
    try {
      return headers.get(name)
    } catch {
      return null
    }
  }
  return { method, path, header, names: null }
}

/*
 * The view of `request`. `rawHeaders` (Node's flat list) gives the header lines in their order when the request itself
 * is a Fetch Request that lost it.
 */
function viewOf(request, rawHeaders) {
  const method = String(request.method || "GET").toUpperCase()
  const path = pathOf(request.originalUrl || request.url || request.path)
  if (Array.isArray(rawHeaders)) return linesView(method, path, pairsOf(rawHeaders), true)
  if (Array.isArray(request.rawHeaders)) return linesView(method, path, pairsOf(request.rawHeaders), true)
  if (Array.isArray(request.headers)) return linesView(method, path, request.headers, true)
  if (request.headers && typeof request.headers.get === "function") return headersView(method, path, request.headers)
  return linesView(method, path, Object.entries(request.headers || {}), false)
}

/*
 * The request as botscent's server inspect() reads one: a Fetch Request as it is, anything else as
 * { headers, method, url } (what botscent's own Express adapter passes).
 */
function botscentRequestOf(request) {
  if (request.headers && typeof request.headers.get === "function") return request
  const headers = Array.isArray(request.headers) ? Object.fromEntries(request.headers.map(([name, value]) => [String(name).toLowerCase(), value])) : request.headers
  return { headers: headers || {}, method: request.method || "GET", url: request.originalUrl || request.url || request.path || "/" }
}

/*
 * The visitor's address from the site's clientIp(subject), or null: no clientIp, an answer that is not text, or a
 * clientIp that throws. No address means no network key; the page still gets its token.
 */
function addressOf(clientIp, subject) {
  if (typeof clientIp !== "function") return null
  try {
    const ip = clientIp(subject)
    return typeof ip === "string" ? ip : null
  } catch {
    return null
  }
}

module.exports = { viewOf, botscentRequestOf, addressOf }
