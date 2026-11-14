"use strict"
/*
 * facts.js — which requests get a token, and what the token says about the request.
 *
 * A token goes on the response to a top-level page request only: a GET whose Sec-Fetch-Dest is "document", or, from a
 * client that sends no fetch metadata, a GET that accepts text/html. Never a frame, a subresource, a POST or a HEAD, a
 * static file (the extension list in defaults.json follows @knownagents/sdk 3.1.0 src/paths.ts, Apache-2.0; the rule
 * only) or a dot-file. A prefetch or prerender of a page gets one too, with its Sec-Purpose: the browser shows that very
 * response if the visitor goes to the page, and cake then knows the Sec-Fetch values describe the speculative request.
 *
 * The facts are request headers the browser sends anyway (the page's scripts can learn most of them other ways), cut to
 * the lengths in defaults.json with control characters removed, the header names in order (never their values), whether
 * a Web Bot Auth signature came along, and botscent's verdict in its own vocabulary. Never an IP address, a cookie or an
 * authorization value. Adapted from tartini.ai's cake-server-timing.js (toast_mvp branch cake-tartini, 01eafdb7).
 * Step S4.1.
 */
const CONTROL = /[\u0000-\u001f\u007f]/g
const HEADER_NAME = /^[a-z0-9-]+$/
const IDENTIFIER = /^[a-z0-9][a-z0-9._-]*$/i
const VERSION = /^[0-9A-Za-z.+-]+$/
const OWS = /^[\t ]+|[\t ]+$/g // HTTP's optional whitespace; String.trim would also take other Unicode spaces, Python's strip others again

// The media types an Accept value lists, lower-cased, without parameters.
function mediaTypes(accept) {
  return new Set(String(accept || "").split(",").map((range) => range.split(";")[0].replace(OWS, "").toLowerCase()))
}

// A dot-file (a path segment starting with ".") or a static file by its extension.
function isSkippedPath(path, settings) {
  const lower = path.toLowerCase()
  if (lower.split("/").some((segment) => segment.startsWith("."))) return true
  return settings.skip_extensions.some((extension) => lower.endsWith(extension))
}

function isPageRequest(view, settings) {
  const { fixed, headers } = settings
  if (view.method !== fixed.page_method) return false
  const dest = view.header(headers.sec_fetch_dest)
  const isDocument = dest !== null ? dest.toLowerCase() === fixed.page_dest : mediaTypes(view.header(headers.accept)).has(fixed.page_type)
  return isDocument && !isSkippedPath(view.path, settings)
}

// A value without control characters, at most `length` characters long (counted by code point, as Python counts).
function cut(value, length) {
  if (value === null || value === undefined) return null
  const clean = String(value).replace(CONTROL, "")
  return clean.length <= length ? clean : Array.from(clean).slice(0, length).join("")
}

function headerNames(view, settings) {
  if (!view.names) return null
  const names = []
  for (const name of view.names) {
    if (names.length >= settings.max_header_names) break
    if (name.length <= settings.cut.header_name && HEADER_NAME.test(name)) names.push(name)
  }
  return names
}

// The payload's fields that describe the request, in the format's order: p, sf, sp, md, al, ch, ua, hn, sg.
function requestFacts(view, settings) {
  const { headers: names, cut: lengths, fixed } = settings
  const header = (role, length) => cut(view.header(names[role]), length)
  return {
    p: cut(view.path, lengths.path),
    sf: {
      s: header("sec_fetch_site", lengths.sec_fetch),
      m: header("sec_fetch_mode", lengths.sec_fetch),
      d: header("sec_fetch_dest", lengths.sec_fetch),
      u: header("sec_fetch_user", lengths.sec_fetch_user),
    },
    sp: header("sec_purpose", lengths.sec_purpose),
    md: mediaTypes(view.header(names.accept)).has(fixed.markdown_type),
    al: header("accept_language", lengths.accept_language),
    ch: {
      ua: header("sec_ch_ua", lengths.sec_ch_ua),
      pf: header("sec_ch_ua_platform", lengths.sec_ch_ua_platform),
      mb: header("sec_ch_ua_mobile", lengths.sec_ch_ua_mobile),
    },
    ua: header("user_agent", lengths.user_agent),
    hn: headerNames(view, settings),
    sg: {
      a: header("signature_agent", lengths.signature_agent),
      s: view.header(names.signature) !== null,
      i: view.header(names.signature_input) !== null,
    },
  }
}

// botscent's verdict ({ type, agent_name, reasons }) as { t, a, r }, keeping only short identifiers; null when none.
function verdictFields(verdict, fixed) {
  if (!verdict || !fixed.verdict_types.includes(verdict.type)) return null
  const identifier = (value) => (typeof value === "string" && value.length <= fixed.verdict_id_max && IDENTIFIER.test(value) ? value : null)
  const reasons = Array.isArray(verdict.reasons) ? verdict.reasons.map(identifier).filter(Boolean).slice(0, fixed.verdict_reasons_max) : []
  return { t: verdict.type, a: identifier(verdict.agent_name), r: reasons }
}

function versionOf(version, fixed) {
  return typeof version === "string" && version.length <= fixed.version_max && VERSION.test(version) ? version : null
}

module.exports = { isPageRequest, requestFacts, verdictFields, versionOf }
