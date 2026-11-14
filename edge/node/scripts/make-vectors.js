"use strict"
/*
 * make-vectors.js — writes tests/vectors/edge_token.json, the test vectors every site middleware and cake share.
 *
 *   node edge/node/scripts/make-vectors.js
 *
 * Every vector is made by this package (index.js) from the fixed inputs below, so the same inputs write the same file.
 * Run it only when the token's format changes on purpose; every middleware's tests and cake's then show what changed.
 * The secrets are for tests only.
 */
const fs = require("node:fs")
const path = require("node:path")
const { fixed } = require("../defaults.json")
const { mintToken, signPayload, verifyToken, networkKey, ipPrefix } = require("..")
const { encodeBase64Url } = require("../lib/token")
const { webMac } = require("../lib/web-crypto")

const OUT = path.join(__dirname, "..", "..", "..", "tests", "vectors", "edge_token.json")
const SECRETS = {
  main: "test-only secret for the shared vectors, never used anywhere else",
  other: "a second test-only secret, to show a token signed with another key",
  tartini: "k".repeat(48),
}
const NOW = Date.UTC(2026, 10, 12, 17, 0, 0)
const MINUTE = 60 * 1000
const DAY = 24 * 60 * MINUTE
const IPV4 = "203.0.113.77" // RFC 5737 documentation range: nobody's address
const IPV6 = "2001:db8:abcd:12::1" // RFC 3849 documentation range

const CHROME_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
const CHROME_HINTS = [
  ["sec-ch-ua", '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'],
  ["sec-ch-ua-mobile", "?0"],
  ["sec-ch-ua-platform", '"macOS"'],
]
const HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"

// A Chrome navigation's header lines, in Chrome's order, with the fetch metadata given (null leaves a line out).
function chrome({ site = "none", user = "?1", purpose = null, extra = [] } = {}) {
  const fetchMetadata = [["Sec-Fetch-Site", site], ["Sec-Fetch-Mode", "navigate"], ["Sec-Fetch-User", user], ["Sec-Fetch-Dest", "document"]]
  return [
    ["Host", "shop.example"],
    ["Connection", "keep-alive"],
    ...CHROME_HINTS,
    ["Upgrade-Insecure-Requests", "1"],
    ["User-Agent", CHROME_UA],
    ["Accept", HTML_ACCEPT],
    ...(purpose ? [["Sec-Purpose", purpose]] : []),
    ...fetchMetadata.filter(([, value]) => value !== null),
    ...extra,
    ["Accept-Encoding", "gzip, deflate, br, zstd"],
    ["Accept-Language", "en-US,en;q=0.9"],
  ]
}

const SAFARI_15 = [
  ["Host", "shop.example"],
  ["Connection", "keep-alive"],
  ["Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"],
  ["User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15"],
  ["Accept-Language", "en-GB,en;q=0.9"],
  ["Accept-Encoding", "gzip, deflate, br"],
]

const page = (name, request, extra = {}) => ({ name, secret: "main", now_ms: NOW, client_ip: IPV4, verdict: null, version: null, request, ...extra })
const get = (path, headers) => ({ method: "GET", path, headers })

const MINT = [
  page("Chrome, address typed: Sec-Fetch-Site none, Sec-Fetch-User ?1", get("/", chrome())),
  page("Chrome, a link on the same site, with a query the token leaves out", get("/products/cake?ref=home", chrome({ site: "same-origin", extra: [["Referer", "https://shop.example/"]] }))),
  page("first page from another site, no user activation (what Claude in Chrome's first page looks like)", get("/", chrome({ site: "cross-site", user: null }))),
  page("a signed agent: Signature-Agent kept as sent, Signature and Signature-Input only as present", get("/", chrome({
    site: "cross-site",
    user: null,
    extra: [["Signature-Agent", '"https://chatgpt.com"'], ["Signature-Input", 'sig1=("@authority" "signature-agent");created=1794502790;keyid="k1";tag="web-bot-auth"'], ["Signature", "sig1=:dGVzdC1vbmx5LXNpZ25hdHVyZQ==:"]],
  }))),
  page("a prerender: Sec-Purpose recorded, no user activation", get("/next", chrome({ site: "same-origin", user: null, purpose: "prefetch;prerender" }))),
  page("Safari 15, no fetch metadata, accepts text/html; an IPv6 client", get("/", SAFARI_15), { client_ip: IPV6 }),
  page("an agent asking for markdown first", get("/", [["Host", "shop.example"], ["Connection", "keep-alive"], ["User-Agent", "ExampleAgent/1.0"], ["Accept", "text/markdown, text/html;q=0.9"]])),
  page("long values cut, control characters removed", get(`/${"p".repeat(240)}`, chrome({ extra: [["X-Long", "x".repeat(300)]] }).map(([name, value]) =>
    name === "User-Agent" ? [name, `${CHROME_UA} ${"A".repeat(300)}`] : name === "Accept-Language" ? [name, "en\u0007-US,\u001fen;q=0.9"] : [name, value]))),
  page("a header line sent twice is joined with ', '", get("/", [...chrome(), ["Accept-Language", "fr;q=0.5"]])),
  page("more header lines than the token keeps names of", get("/", [...chrome(), ...Array.from({ length: 30 }, (_, n) => [`X-Extra-${n}`, `extra-${n}`])])),
  page("no client address: no network key", get("/", chrome()), { client_ip: null }),
  page("an IPv4-mapped IPv6 client has its IPv4 network key", get("/", chrome()), { client_ip: `::ffff:${IPV4}` }),
  page("botscent's verdict and version", get("/", chrome()), { verdict: { type: "agent", agent_name: "claude-in-chrome", reasons: ["extension-marker", "not an id!"] }, version: "1.2.0" }),
  page("a value with a Latin-1 character (UTF-8 in the JSON)", get("/", chrome({ extra: [["Signature-Agent", '"https://agent.example/café"']] }))),
  page("signed with the other secret", get("/", chrome()), { secret: "other" }),
  page("the path as sent: a target starting with // is a path, not a host", get("//shop/about?x=1", chrome())),
  page("not a page: dot segments are not resolved, and a segment starting with . is a dot-file", get("/a/b/..", chrome())),
  page("not a page: a POST", { method: "POST", path: "/", headers: chrome() }),
  page("not a page: a HEAD", { method: "HEAD", path: "/", headers: chrome() }),
  page("not a page: a frame", get("/", chrome().map(([name, value]) => (name === "Sec-Fetch-Dest" ? [name, "iframe"] : [name, value])))),
  page("not a page: a script", get("/app", chrome().map(([name, value]) => (name === "Sec-Fetch-Dest" ? [name, "script"] : [name, value])))),
  page("not a page: a fetch() call", get("/api/cart", chrome().map(([name, value]) => (name === "Sec-Fetch-Dest" ? [name, "empty"] : [name, value])))),
  page("not a page: an image opened in a tab", get("/logo.png", chrome())),
  page("not a page: a dot-file", get("/.well-known/security.txt", chrome())),
  page("not a page: a client that does not ask for HTML", get("/", [["Host", "shop.example"], ["User-Agent", "curl/8.7.1"], ["Accept", "*/*"]])),
]

async function mintVectors() {
  const out = []
  for (const [n, input] of MINT.entries()) {
    const id = `vector-${String(n + 1).padStart(2, "0")}`
    const token = await mintToken(SECRETS[input.secret], input.request, { nowMs: input.now_ms, id, ip: input.client_ip, verdict: input.verdict, version: input.version })
    const payload = token ? (await verifyToken(SECRETS[input.secret], token, { nowMs: input.now_ms })).payload : null
    out.push({ name: input.name, secret: input.secret, now_ms: input.now_ms, id, client_ip: input.client_ip, verdict: input.verdict, version: input.version, request: input.request, payload, token })
  }
  return out
}

// The text with its character at `at` replaced by another base64url character.
function changed(text, at) {
  return `${text.slice(0, at)}${text[at] === "A" ? "B" : "A"}${text.slice(at + 1)}`
}

async function signedBody(secret, bodyText) {
  const body = encodeBase64Url(new TextEncoder().encode(bodyText))
  const mac = await webMac(new TextEncoder().encode(secret))(`${fixed.token_prefix}.${body}`)
  return `${fixed.token_prefix}.${body}.${encodeBase64Url(mac)}`
}

async function verifyVectors(mint) {
  const token = mint[0].token
  const [prefix, body, mac] = token.split(".")
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
  const withDash = mint.find((vector) => vector.token && /[-_]/.test(vector.token.split(".")[2]))
  const tartini = "c1.eyJ2IjoxLCJpZCI6InZlY3Rvci0xIiwidCI6MTc5NDUwMjgwMDAwMCwicCI6Ii8iLCJicyI6eyJ0IjoiYWdlbnQiLCJhIjoiY2xhdWRlLWluLWNocm9tZSIsInIiOlsiZXh0ZW5zaW9uLW1hcmtlciJdfSwiaWsiOiIzMGZhOGNlMTFiN2E2YzJhIn0.ECFhiDnT7T0k45nKX4Vl4Z5ZaOaqBzKDynVqsUm_Y6Q"
  const cases = [
    ["a page token at its own time", "main", token, NOW],
    ["at the end of the window", "main", token, NOW + fixed.verify_max_age_ms],
    ["one millisecond past the window", "main", token, NOW + fixed.verify_max_age_ms + 1],
    ["a clock up to a minute ahead", "main", token, NOW - fixed.verify_max_future_ms],
    ["more than a minute before the token's time", "main", token, NOW - fixed.verify_max_future_ms - 1],
    ["one character of the payload changed", "main", `${prefix}.${changed(body, 20)}.${mac}`, NOW],
    ["one character of the MAC changed", "main", `${prefix}.${body}.${changed(mac, 7)}`, NOW],
    ["signed with another secret", "main", mint.find((vector) => vector.secret === "other").token, NOW],
    ["another prefix", "main", `c2.${body}.${mac}`, NOW],
    ["two parts", "main", `${prefix}.${body}`, NOW],
    ["four parts", "main", `${token}.${mac}`, NOW],
    ["padding after the MAC", "main", `${token}=`, NOW],
    ["the MAC spelled with a spare bit set", "main", `${prefix}.${body}.${mac.slice(0, -1)}${alphabet[alphabet.indexOf(mac[mac.length - 1]) + 1]}`, NOW],
    ["the MAC in the standard base64 alphabet", "main", withDash.token.replace(/\.([^.]*)$/, (whole, m) => `.${m.replace(/-/g, "+").replace(/_/g, "/")}`), NOW],
    ["a character outside base64url in the payload", "main", `${prefix}.${body.slice(0, 5)}*${body.slice(6)}.${mac}`, NOW],
    ["empty", "main", "", NOW],
    ["a good MAC over text that is not JSON", "main", await signedBody(SECRETS.main, "not json"), NOW],
    ["a good MAC over a JSON array", "main", await signPayload(SECRETS.main, [1, 2]), NOW],
    ["a good MAC over a payload without an id", "main", await signPayload(SECRETS.main, { v: 1, t: NOW }), NOW],
    ["a good MAC over a payload whose time is not an integer", "main", await signPayload(SECRETS.main, { v: 1, id: "x", t: NOW + 0.5 }), NOW],
    ["a good MAC over a payload of another version", "main", await signPayload(SECRETS.main, { v: 2, id: "x", t: NOW }), NOW],
    ["a good MAC over the smallest payload there is", "main", await signPayload(SECRETS.main, { v: 1, id: "x", t: NOW }), NOW],
    ["the token of tartini.ai's middleware and cake 0.3.3", "tartini", tartini, NOW],
  ]
  const out = []
  for (const [name, secret, candidate, nowMs] of cases) {
    const { result, payload } = await verifyToken(SECRETS[secret], candidate, { nowMs })
    out.push({ name, secret, token: candidate, now_ms: nowMs, result, ...(result === "ok" ? { payload } : {}) })
  }
  return out
}

async function networkKeyVectors() {
  const cases = [
    ["IPv4", "main", IPV4, NOW],
    ["the same /24", "main", "203.0.113.5", NOW],
    ["another /24", "main", "203.0.114.77", NOW],
    ["the next UTC day", "main", IPV4, NOW + DAY],
    ["spaces around the address", "main", ` ${IPV4} `, NOW],
    ["IPv4-mapped IPv6, dotted", "main", `::ffff:${IPV4}`, NOW],
    ["IPv4-mapped IPv6, in hex", "main", "::ffff:cb00:714d", NOW],
    ["IPv6", "main", IPV6, NOW],
    ["IPv6 with a zero third group", "main", "2001:db8::1", NOW],
    ["IPv6 in capitals with leading zeros", "main", "2001:0DB8:00ab:ffff::", NOW],
    ["IPv6 with a zone", "main", "fe80::1%eth0", NOW],
    ["IPv6 loopback", "main", "::1", NOW],
    ["an IPv4 tail that is not mapped", "main", "::ffff:0:1.2.3.4", NOW],
    ["cake 0.3.3 and tartini.ai's key", "tartini", IPV4, NOW],
    ["an octet over 255", "main", "256.1.1.1", NOW],
    ["a leading zero", "main", "01.2.3.4", NOW],
    ["with a port", "main", "1.2.3.4:80", NOW],
    ["in brackets", "main", "[2001:db8::1]", NOW],
    ["two ::", "main", "2001:db8::1::2", NOW],
    ["a mapped tail with a leading zero", "main", "::ffff:1.2.3.04", NOW],
    ["an empty zone", "main", "fe80::1%", NOW],
    ["a slash in the zone", "main", "fe80::1%eth/0", NOW],
    ["empty", "main", "", NOW],
    ["not an address", "main", "unknown", NOW],
  ]
  const out = []
  for (const [name, secret, ip, nowMs] of cases) {
    out.push({ name, secret, ip, now_ms: nowMs, prefix: ipPrefix(ip), key: await networkKey(SECRETS[secret], ip, nowMs) })
  }
  return out
}

async function main() {
  const mint = await mintVectors()
  const vectors = {
    about: [
      "Shared test vectors for AgentCake's server-half token: every site middleware (edge/node, edge/python, edge/php and",
      "the WordPress plugin that carries it) and cake's own maker and verifier (agentcake/edge_token.py) must reproduce",
      "them. The secrets are for tests only and are never used anywhere else. Written by edge/node/scripts/make-vectors.js;",
      "checked by edge/node/test/vectors.test.js, tests/test_edge_vectors.py, tests/test_edge_python.py and",
      "edge/php/tests/vectors_test.php.",
      "mint: a request, a time, a token id and a client address make `token` (null: the request gets none); `payload` is",
      "what the token holds. verify: `result` is what cake concludes at `now_ms` (ok, stale or bad). network_keys: the",
      "prefix and key of an address on a day (null: not an address).",
    ],
    rules: {
      token_prefix: fixed.token_prefix,
      payload_version: fixed.payload_version,
      max_age_ms: fixed.verify_max_age_ms,
      max_future_ms: fixed.verify_max_future_ms,
      network_key_label: fixed.network_key_label,
      network_key_hex_chars: fixed.network_key_hex_chars,
      ipv4_prefix_bits: fixed.ipv4_prefix_bits,
      ipv6_prefix_bits: fixed.ipv6_prefix_bits,
    },
    secrets: SECRETS,
    mint,
    verify: await verifyVectors(mint),
    network_keys: await networkKeyVectors(),
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true })
  fs.writeFileSync(OUT, `${JSON.stringify(vectors, null, 2)}\n`)
  console.log(`${path.relative(process.cwd(), OUT)}: ${vectors.mint.length} mint, ${vectors.verify.length} verify, ${vectors.network_keys.length} network key vectors`)
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
