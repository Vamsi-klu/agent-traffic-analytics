"use strict"
/*
 * timing.js — the response side: a Server-Timing value with cake's entry in it, whether a response is HTML, and a Fetch
 * Response with both set.
 *
 * A Server-Timing value is a list of entries split at commas outside quoted strings. `entries` is adapted from botscent
 * (https://github.com/nalinbhardwaj/botscent, src/server/timing.ts, commit 7f948003, Copyright (c) 2026 Nalin Bhardwaj,
 * MIT License). Any cake entry already in the value (from a proxy, a second copy of this middleware or a stored
 * response) is dropped and this request's entry goes last, so a response carries exactly one. botscent's Next.js and
 * Hono adapters copy a response whose headers cannot change; responseWith does the same. Step S4.1.
 */
function entries(value) {
  const out = []
  let start = 0
  let quoted = false
  for (let i = 0; i < value.length; i++) {
    const char = value[i]
    if (quoted && char === "\\") i++
    else if (char === '"') quoted = !quoted
    else if (char === "," && !quoted) {
      out.push(value.slice(start, i))
      start = i + 1
    }
  }
  out.push(value.slice(start))
  return out.map((entry) => entry.trim()).filter(Boolean)
}

function isCakeEntry(entry, fixed) {
  return entry.split(";", 1)[0].trim().toLowerCase() === fixed.entry_name
}

// `value` (a response's Server-Timing, or nothing) with this token's entry in place of any cake entry.
function withCakeEntry(value, token, fixed) {
  const kept = value ? entries(String(value)).filter((entry) => !isCakeEntry(entry, fixed)) : []
  return [...kept, `${fixed.entry_name};desc="${token}"`].join(", ")
}

function isHtml(contentType, fixed) {
  const type = String(contentType || "").split(";")[0].trim().toLowerCase()
  return fixed.html_types.includes(type)
}

/*
 * A Fetch Response carrying the entry, and Cache-Control private, no-store when `noStore` says so. A response whose
 * headers cannot change (a fetch() result, Response.redirect) is copied first, never thrown on.
 */
function responseWith(response, token, settings, noStore) {
  const { headers: names, fixed } = settings
  const apply = (headers) => {
    headers.set(names.server_timing, withCakeEntry(headers.get(names.server_timing), token, fixed))
    if (noStore) headers.set(names.cache_control, fixed.no_store_value)
  }
  try {
    apply(response.headers)
    return response
  } catch {
    const copy = new Response(response.body, response)
    apply(copy.headers)
    return copy
  }
}

module.exports = { withCakeEntry, isHtml, responseWith }
