"use strict"
/*
 * settings.js — every value one mounting uses: defaults.json and headers.json, with the site's own choices on top, and
 * the secret.
 *
 * A site changes the values under "options" when it mounts the middleware, by their camelCase names (secretEnv, noStore,
 * verdictWaitMs, maxHeaderNames, cut, skipExtensions). The values under "fixed" belong to the token's format and meaning,
 * which cake's verifier and the shared vectors (tests/vectors/edge_token.json) hold too, so no option changes them. An
 * option of the wrong kind keeps its default and is named in one warning, as is an option nobody knows: a mistake in the
 * site's setup must cost the site its token, never its pages. Step S4.1.
 */
const DEFAULTS = require("../defaults.json")
const HEADERS = require("../headers.json")

// The camelCase option a site passes, its key under "options" in defaults.json, and what a value of the right kind is.
const OPTIONS = {
  secretEnv: ["secret_env", (value) => typeof value === "string" && value.length > 0],
  noStore: ["no_store", (value) => typeof value === "boolean"],
  verdictWaitMs: ["verdict_wait_ms", (value) => Number.isFinite(value) && value >= 0],
  maxHeaderNames: ["max_header_names", (value) => Number.isInteger(value) && value >= 0],
  cut: ["cut", (value) => isPlainObject(value) && Object.entries(value).every(([key, length]) => key in DEFAULTS.options.cut && Number.isInteger(length) && length > 0)],
  skipExtensions: ["skip_extensions", (value) => Array.isArray(value) && value.every((extension) => typeof extension === "string")],
}
// Options that wire the middleware to the site rather than tune it; now, randomId and warn let tests pin the clock, the
// token id and the warnings.
const WIRING = new Set(["secret", "clientIp", "botscent", "now", "randomId", "warn"])

const encoder = new TextEncoder()

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

/*
 * The settings of one mounting: the "options" values as chosen, `fixed`, `headers` (the header names), `messages`, and
 * the options that were not known (`unknown`) or not of the right kind (`invalid`).
 */
function settingsFrom(options = {}) {
  const chosen = { ...DEFAULTS.options, cut: { ...DEFAULTS.options.cut } }
  const unknown = []
  const invalid = []
  for (const [name, value] of Object.entries(options)) {
    if (WIRING.has(name) || value === undefined) continue
    if (!(name in OPTIONS)) {
      unknown.push(name)
      continue
    }
    const [key, isRightKind] = OPTIONS[name]
    if (!isRightKind(value)) invalid.push(name)
    else if (key === "cut") Object.assign(chosen.cut, value)
    else chosen[key] = value
  }
  return Object.freeze({
    ...chosen,
    skip_extensions: chosen.skip_extensions.map((extension) => extension.toLowerCase()),
    fixed: DEFAULTS.fixed,
    headers: HEADERS,
    messages: DEFAULTS.messages,
    unknown,
    invalid,
  })
}

// The secret as given, else from the bindings a runtime hands over (Workers' env), else from the process environment.
function resolveSecret(given, settings, env) {
  if (given !== undefined) return given
  if (env && typeof env[settings.secret_env] === "string") return env[settings.secret_env]
  const environment = globalThis.process && globalThis.process.env
  return environment ? environment[settings.secret_env] : undefined
}

// The secret's bytes, or null when there is none or it is shorter than fixed.min_secret_bytes.
function secretBytes(secret, fixed) {
  let bytes = null
  if (typeof secret === "string") bytes = encoder.encode(secret)
  else if (ArrayBuffer.isView(secret)) bytes = new Uint8Array(secret.buffer, secret.byteOffset, secret.byteLength)
  return bytes && bytes.length >= fixed.min_secret_bytes ? bytes : null
}

// A secret that is there but too short: worth one warning, since the site meant to turn the server half on.
function isShortSecret(secret, fixed) {
  const given = typeof secret === "string" ? secret.length > 0 : ArrayBuffer.isView(secret) && secret.byteLength > 0
  return given && secretBytes(secret, fixed) === null
}

function message(settings, name, values = {}) {
  return settings.messages[name].replace(/\{(\w+)\}/g, (whole, key) => (key in values ? String(values[key]) : whole))
}

// What to say once when a mounting starts. The secret itself is never part of a message.
function startupWarnings(settings, secret) {
  const lines = []
  if (isShortSecret(secret, settings.fixed)) lines.push(message(settings, "short_secret", { min: settings.fixed.min_secret_bytes }))
  if (settings.unknown.length) lines.push(message(settings, "unknown_options", { names: settings.unknown.join(", ") }))
  if (settings.invalid.length) lines.push(message(settings, "invalid_options", { names: settings.invalid.join(", ") }))
  return lines
}

// A warn(line) that says each distinct line once: a misconfigured site would otherwise log it on every page.
function warnOnce(options) {
  const warn = typeof options.warn === "function" ? options.warn : (line) => console.warn(line)
  const said = new Set()
  return (line) => {
    if (said.has(line)) return
    said.add(line)
    warn(line)
  }
}

module.exports = { settingsFrom, resolveSecret, secretBytes, isShortSecret, message, startupWarnings, warnOnce }
