"use strict"
/*
 * facts.test.js — which requests get a token, and what the token says about the request: only what the browser sent,
 * cut short, never an IP address, a cookie or an authorization value.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const { options } = require("../defaults.json")
const { mintToken, isPageRequest } = require("..")
const { SECRET, NOW, CLIENT_IP, CHROME_PAGE, withHeaders, plainRequest, fetchRequest, payloadOf } = require("./helpers")

const facts = async (request, extra = {}) => payloadOf(await mintToken(SECRET, request, { nowMs: NOW, id: "id-1", ip: CLIENT_IP, ...extra }))
const NO_FETCH_METADATA = { "sec-fetch-site": null, "sec-fetch-mode": null, "sec-fetch-user": null, "sec-fetch-dest": null }

test("a top-level page gets a token: Sec-Fetch-Dest document, or a GET accepting text/html without fetch metadata", async () => {
  assert.equal(isPageRequest(plainRequest("/")), true, "Chrome's navigation")
  assert.equal(isPageRequest(fetchRequest("/products/cake")), true, "the same as a Fetch Request")
  assert.equal(isPageRequest(plainRequest("/about.html")), true, "a .html page")
  const old = withHeaders(CHROME_PAGE, { ...NO_FETCH_METADATA, accept: "text/html;q=0.9, */*;q=0.8" })
  assert.equal(isPageRequest(plainRequest("/", old)), true, "a browser without fetch metadata")
  assert.ok(await mintToken(SECRET, plainRequest("/"), { nowMs: NOW }), "and a page gets a token")
})

test("never a frame, a subresource, a POST, a HEAD, a static file, a dot-file or a client that does not ask for HTML", async () => {
  for (const [why, request] of [
    ["a frame", plainRequest("/", withHeaders(CHROME_PAGE, { "sec-fetch-dest": "iframe" }))],
    ["a script", plainRequest("/app", withHeaders(CHROME_PAGE, { "sec-fetch-dest": "script" }))],
    ["a fetch() call", plainRequest("/api/cart", withHeaders(CHROME_PAGE, { "sec-fetch-dest": "empty" }))],
    ["a POST", plainRequest("/", CHROME_PAGE, "POST")],
    ["a HEAD", plainRequest("/", CHROME_PAGE, "HEAD")],
    ["an image opened in a tab", plainRequest("/logo.PNG")],
    ["a stylesheet", plainRequest("/assets/site.css")],
    ["a dot-file", plainRequest("/.well-known/security.txt")],
    ["curl", plainRequest("/", [["Host", "shop.example"], ["User-Agent", "curl/8.7.1"], ["Accept", "*/*"]])],
    ["no Accept at all", plainRequest("/", withHeaders(CHROME_PAGE, { ...NO_FETCH_METADATA, accept: null }))],
  ]) {
    assert.equal(isPageRequest(request), false, why)
    assert.equal(await mintToken(SECRET, request, { nowMs: NOW }), null, why)
  }
})

test("a prefetch or prerender of a page gets a token that says so, since the browser shows it if the visitor goes there", async () => {
  const prerender = plainRequest("/next", withHeaders(CHROME_PAGE, { "sec-purpose": "prefetch;prerender", "sec-fetch-user": null }))
  assert.equal(isPageRequest(prerender), true)
  const payload = await facts(prerender)
  assert.equal(payload.sp, "prefetch;prerender")
  assert.equal(payload.sf.u, null, "no user activation on a speculative request")
  assert.equal((await facts(plainRequest("/"))).sp, null, "an ordinary navigation has none")
})

test("the facts: Sec-Fetch values, markdown, language, client hints, user agent, header names in order, Web Bot Auth", async () => {
  const signed = withHeaders(CHROME_PAGE, {
    "sec-fetch-site": "cross-site",
    "sec-fetch-user": null,
    "signature-agent": '"https://chatgpt.com"',
    signature: "sig1=:AAAA:",
    "signature-input": 'sig1=("@authority");created=1',
  })
  const payload = await facts(plainRequest("/products/cake", signed))
  assert.equal(payload.p, "/products/cake")
  assert.deepEqual(payload.sf, { s: "cross-site", m: "navigate", d: "document", u: null })
  assert.equal(payload.md, false)
  assert.equal(payload.al, "en-US,en;q=0.9")
  assert.deepEqual(payload.ch, { ua: '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"', pf: '"macOS"', mb: "?0" })
  assert.match(payload.ua, /Chrome\/142/)
  assert.deepEqual(payload.sg, { a: '"https://chatgpt.com"', s: true, i: true })
  assert.deepEqual(payload.hn.slice(0, 4), ["host", "connection", "sec-ch-ua", "sec-ch-ua-mobile"], "names in the order sent")
  assert.equal((await facts(plainRequest("/"))).sg.s, false, "no signature: false")
  const markdown = withHeaders(CHROME_PAGE, { ...NO_FETCH_METADATA, accept: "text/markdown, text/html;q=0.9" })
  assert.equal((await facts(plainRequest("/", markdown))).md, true, "an agent asking for markdown")
})

test("a Fetch Request does not keep the order of its headers, so its names are null rather than sorted", async () => {
  assert.equal((await facts(fetchRequest("/"))).hn, null)
  const flat = CHROME_PAGE.flatMap(([name, value]) => [name, value])
  assert.equal((await facts(fetchRequest("/"), { rawHeaders: flat })).hn[0], "host", "unless the raw lines are handed over")
})

test("long and control-character values are cut, never passed whole", async () => {
  const noisy = withHeaders(CHROME_PAGE, { "user-agent": "A".repeat(5000), "accept-language": "en\u0007-US,".repeat(30) })
  const payload = await facts(plainRequest(`/${"p".repeat(500)}`, noisy))
  assert.equal(payload.ua.length, options.cut.user_agent)
  assert.ok(payload.al.length <= options.cut.accept_language)
  assert.doesNotMatch(payload.al, /[\u0000-\u001f]/)
  assert.equal(payload.p.length, options.cut.path)
})

test("header names: names only, in the order sent, at most the configured number", async () => {
  const many = [...CHROME_PAGE, ...Array.from({ length: 60 }, (_, n) => [`X-Extra-${n}`, `value-${n}`])]
  const payload = await facts(plainRequest("/", many))
  assert.equal(payload.hn.length, options.max_header_names)
  assert.equal(payload.hn[CHROME_PAGE.length], "x-extra-0")
  assert.ok(!JSON.stringify(payload.hn).includes("value-"), "never a value")
  assert.equal((await facts(plainRequest("/", many), { maxHeaderNames: 3 })).hn.length, 3, "a site can choose fewer")
})

test("repeated header lines are joined with ', ' the way Fetch joins them, on every runtime", async () => {
  const twice = [...CHROME_PAGE, ["Accept-Language", "fr"]]
  assert.equal((await facts(plainRequest("/", twice))).al, "en-US,en;q=0.9, fr")
  assert.equal((await facts(fetchRequest("/", twice))).al, "en-US,en;q=0.9, fr")
})

test("the token holds no IP address, no cookie and no authorization value", async () => {
  const sensitive = withHeaders(CHROME_PAGE, { cookie: "session=s3cr3t-cookie", authorization: "Bearer s3cr3t-bearer", "x-forwarded-for": CLIENT_IP })
  const text = JSON.stringify(await facts(plainRequest("/", sensitive)))
  for (const leak of ["203.0.113", "s3cr3t-cookie", "s3cr3t-bearer"]) assert.ok(!text.includes(leak), leak)
  const v6 = JSON.stringify(await facts(plainRequest("/"), { ip: "2001:db8:abcd:12::1" }))
  assert.ok(!v6.includes("2001:db8"), "nor an IPv6 address or its prefix")
  assert.match(JSON.parse(v6).ik, /^[0-9a-f]{16}$/, "only the keyed network key")
})

test("the payload holds exactly the documented fields, so whoever reads the page learns no more", async () => {
  const payload = await facts(plainRequest("/"))
  assert.deepEqual(Object.keys(payload), ["v", "id", "t", "p", "sf", "sp", "md", "al", "ch", "ua", "hn", "sg", "ik", "bs", "bsv"])
  assert.deepEqual(Object.keys(payload.sf), ["s", "m", "d", "u"])
  assert.deepEqual(Object.keys(payload.ch), ["ua", "pf", "mb"])
  assert.deepEqual(Object.keys(payload.sg), ["a", "s", "i"])
  assert.equal(payload.bs, null, "no verdict without botscent")
  assert.equal(payload.bsv, null)
})

test("botscent's verdict is kept in its own vocabulary only: a type, a name and reason ids", async () => {
  const verdict = { type: "agent", agent_name: "claude-in-chrome", reasons: ["extension-marker", "web-bot-auth", "<script>", 7] }
  const payload = await facts(plainRequest("/"), { verdict, version: "1.2.0" })
  assert.deepEqual(payload.bs, { t: "agent", a: "claude-in-chrome", r: ["extension-marker", "web-bot-auth"] })
  assert.equal(payload.bsv, "1.2.0")
  assert.deepEqual((await facts(plainRequest("/"), { verdict: { type: "human", reasons: [] } })).bs, { t: "human", a: null, r: [] })
  assert.equal((await facts(plainRequest("/"), { verdict: { type: "maybe" }, version: "bad version!" })).bs, null)
  assert.equal((await facts(plainRequest("/"), { version: "bad version!" })).bsv, null)
})
