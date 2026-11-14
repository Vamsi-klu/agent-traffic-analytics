"use strict"
/*
 * express.test.js — the Express / Connect / node:http mounting, over a real HTTP server: one cake entry on each page
 * response, whatever the handlers after it do with Server-Timing; nothing on anything else; nothing at all without a
 * secret; a slow botscent never holds the page; a failure never breaks it; caching left alone unless noStore is on.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const http = require("node:http")
const https = require("node:https")
const net = require("node:net")
const { fixed, options } = require("../defaults.json")
const { cakeExpress } = require("../express")
const { verifyToken } = require("..")
const { SECRET, NOW, CLIENT_IP, CHROME_PAGE, withHeaders, tokenIn, listen, send } = require("./helpers")

const mount = (options = {}) =>
  cakeExpress({ secret: SECRET, now: () => NOW, randomId: () => "id-1", clientIp: () => CLIENT_IP, warn: () => {}, ...options })

const page = (req, res) => {
  res.setHeader("Content-Type", "text/html; charset=utf-8")
  res.end("<!doctype html><title>Shop</title><a href='/next'>next</a>")
}

// A server whose only route runs `app` after the middleware, the way Express runs the routes after app.use().
async function withServer(middleware, app, run) {
  const server = await listen((req, res) => middleware(req, res, () => app(req, res)))
  try {
    await run(server.origin)
  } finally {
    await server.close()
  }
}

const cakeEntries = (serverTiming) => (serverTiming || "").split(",").filter((entry) => entry.trim().startsWith("cake;"))

test("a page served by a later handler gets exactly one cake entry, and its token verifies", async () => {
  await withServer(mount(), page, async (origin) => {
    const res = await send(origin, "/")
    assert.equal(res.status, 200)
    assert.equal(cakeEntries(res.headers["server-timing"]).length, 1)
    const { result, payload } = await verifyToken(SECRET, tokenIn(res.headers["server-timing"]), { nowMs: NOW })
    assert.equal(result, "ok")
    assert.deepEqual(payload.sf, { s: "none", m: "navigate", d: "document", u: "?1" })
    assert.equal(payload.hn[0], "host", "the raw header order of the real request")
  })
})

test("the entry survives a handler that writes its own Server-Timing with setHeader or writeHead", async () => {
  const handlers = {
    setHeader: (req, res) => {
      res.setHeader("Server-Timing", "db;dur=53")
      page(req, res)
    },
    "writeHead with an object": (req, res) => {
      res.writeHead(200, { "Content-Type": "text/html", "Server-Timing": "db;dur=53" })
      res.end("<p>ok</p>")
    },
    "writeHead with a list": (req, res) => {
      res.writeHead(200, "OK", ["Content-Type", "text/html", "Server-Timing", "db;dur=53"])
      res.end("<p>ok</p>")
    },
  }
  for (const [why, handler] of Object.entries(handlers)) {
    await withServer(mount(), handler, async (origin) => {
      const timing = (await send(origin, "/")).headers["server-timing"]
      assert.match(timing, /db;dur=53/, `${why}: the site's own entry is kept`)
      assert.equal(cakeEntries(timing).length, 1, `${why}: and cake's is there once`)
    })
  }
})

test("an inherited cake entry is replaced, never doubled", async () => {
  const stale = (req, res) => {
    res.setHeader("Server-Timing", 'cake;desc="c1.old.old", app;dur=2')
    page(req, res)
  }
  await withServer(mount(), stale, async (origin) => {
    const timing = (await send(origin, "/")).headers["server-timing"]
    assert.equal(cakeEntries(timing).length, 1)
    assert.ok(!timing.includes("c1.old.old"))
    assert.match(timing, /app;dur=2/)
  })
})

test("a static file, a frame, a POST and a HEAD get nothing", async () => {
  await withServer(mount(), page, async (origin) => {
    for (const [why, path, options] of [
      ["a script", "/app.js", { lines: withHeaders(CHROME_PAGE, { "sec-fetch-dest": "script" }) }],
      ["an image opened in a tab", "/logo.png", {}],
      ["a frame", "/", { lines: withHeaders(CHROME_PAGE, { "sec-fetch-dest": "iframe" }) }],
      ["a POST", "/", { method: "POST" }],
      ["a HEAD", "/", { method: "HEAD" }],
    ]) {
      assert.equal((await send(origin, path, options)).headers["server-timing"], undefined, why)
    }
  })
})

test("with no secret, or one shorter than 32 bytes, nothing is sent at all", async () => {
  const warnings = []
  for (const secret of [undefined, "", "too-short-secret"]) {
    const middleware = cakeExpress({ secret, warn: (line) => warnings.push(line) })
    assert.equal(middleware.enabled, false)
    await withServer(middleware, page, async (origin) => {
      assert.equal((await send(origin, "/")).headers["server-timing"], undefined)
    })
  }
  assert.equal(warnings.length, 1, "one warning, for the secret that is there but short")
  const saved = process.env[options.secret_env]
  delete process.env[options.secret_env]
  try {
    assert.equal(cakeExpress({}).enabled, false, "the default reads the variable, and it is unset")
  } finally {
    if (saved !== undefined) process.env[options.secret_env] = saved
  }
})

test("the secret can come from the environment variable named in defaults.json", async () => {
  const name = options.secret_env
  const saved = process.env[name]
  process.env[name] = SECRET
  try {
    const middleware = cakeExpress({ now: () => NOW, warn: () => {} })
    assert.equal(middleware.enabled, true)
    await withServer(middleware, page, async (origin) => {
      const token = tokenIn((await send(origin, "/")).headers["server-timing"])
      assert.equal((await verifyToken(SECRET, token, { nowMs: NOW })).result, "ok")
    })
  } finally {
    if (saved === undefined) delete process.env[name]
    else process.env[name] = saved
  }
})

test("a slow or failing botscent never holds the page: the token goes without its verdict", async () => {
  const never = { inspect: () => new Promise(() => {}), VERSION: "1.2.0" }
  await withServer(mount({ botscent: never, verdictWaitMs: 0 }), page, async (origin) => {
    const { payload } = await verifyToken(SECRET, tokenIn((await send(origin, "/")).headers["server-timing"]), { nowMs: NOW })
    assert.equal(payload.bs, null)
    assert.equal(payload.bsv, "1.2.0")
  })
  const failing = { inspect: async () => { throw new Error("boom") }, VERSION: "1.2.0" }
  await withServer(mount({ botscent: failing }), page, async (origin) => {
    const { payload } = await verifyToken(SECRET, tokenIn((await send(origin, "/")).headers["server-timing"]), { nowMs: NOW })
    assert.equal(payload.bs, null)
  })
  const missing = Promise.reject(new Error("Cannot find package 'botscent'"))
  missing.catch(() => {})
  await withServer(mount({ botscent: missing }), page, async (origin) => {
    assert.equal((await send(origin, "/")).status, 200, "a botscent that cannot be imported is no verdict, not an error")
  })
})

test("botscent's verdict rides the token when it answers in time", async () => {
  const seen = []
  const botscent = {
    inspect: async (request) => {
      seen.push(request)
      return { type: "agent", agent_name: "chatgpt-agent", reasons: ["web-bot-auth"] }
    },
    VERSION: "1.2.0",
  }
  await withServer(mount({ botscent: Promise.resolve(botscent) }), page, async (origin) => {
    const { payload } = await verifyToken(SECRET, tokenIn((await send(origin, "/next?x=1")).headers["server-timing"]), { nowMs: NOW })
    assert.deepEqual(payload.bs, { t: "agent", a: "chatgpt-agent", r: ["web-bot-auth"] })
    assert.equal(seen[0].method, "GET")
    assert.equal(seen[0].url, "/next?x=1", "botscent gets the request as botscent/server reads one")
    assert.equal(seen[0].headers["sec-fetch-dest"], "document")
  })
})

test("a response already sent is left alone, and a failure never breaks the page", async () => {
  await withServer(mount({ clientIp: () => { throw new Error("no address") } }), page, async (origin) => {
    const { payload } = await verifyToken(SECRET, tokenIn((await send(origin, "/")).headers["server-timing"]), { nowMs: NOW })
    assert.equal(payload.ik, null, "no address: no network key, still a token")
  })
  const middleware = mount()
  const sent = { headersSent: true, getHeader: () => undefined, setHeader: () => assert.fail("must not touch a sent response") }
  await new Promise((done) => middleware(fakeRequest(), sent, done))
  // The middleware's own setHeader fails; the handler writes its head with writeHead alone, as it may.
  const refusing = (req, res) => {
    res.setHeader = () => { throw new Error("header refused") }
    res.writeHead(200, { "Content-Type": "text/html" })
    res.end("<p>ok</p>")
  }
  await withServer(mount(), refusing, async (origin) => {
    assert.equal((await send(origin, "/")).status, 200, "a header that cannot be set costs the token, not the page")
  })
})

test("a 304 for a page carries a fresh token too", async () => {
  const revalidated = (req, res) => {
    if (req.headers["if-none-match"] === '"v1"') {
      res.statusCode = 304
      res.end()
      return
    }
    res.setHeader("ETag", '"v1"')
    res.setHeader("Cache-Control", "no-cache")
    page(req, res)
  }
  await withServer(mount({ randomId: (() => { let n = 0; return () => `id-${++n}` })() }), revalidated, async (origin) => {
    const first = await send(origin, "/")
    const again = await send(origin, "/", { lines: [...CHROME_PAGE, ["If-None-Match", '"v1"']] })
    assert.equal(again.status, 304)
    assert.equal(first.headers["cache-control"], "no-cache", "the site's caching is untouched by default")
    const ids = [first, again].map((res) => tokenIn(res.headers["server-timing"]))
    assert.notEqual(ids[0], ids[1])
    assert.equal((await verifyToken(SECRET, ids[1], { nowMs: NOW })).payload.id, "id-2")
  })
})

test("noStore makes HTML private and unstored, and leaves every other type alone", async () => {
  const json = (req, res) => {
    res.setHeader("Content-Type", "application/json")
    res.setHeader("Cache-Control", "max-age=60")
    res.end("{}")
  }
  const cachedPage = (req, res) => {
    res.writeHead(200, { "Content-Type": "text/html", "Cache-Control": "public, max-age=600" })
    res.end("<p>cached</p>")
  }
  await withServer(mount({ noStore: true }), cachedPage, async (origin) => {
    assert.equal((await send(origin, "/")).headers["cache-control"], fixed.no_store_value)
  })
  await withServer(mount({ noStore: true }), json, async (origin) => {
    assert.equal((await send(origin, "/data")).headers["cache-control"], "max-age=60")
  })
  await withServer(mount(), cachedPage, async (origin) => {
    assert.equal((await send(origin, "/")).headers["cache-control"], "public, max-age=600", "off by default")
  })
})

test("the middleware sets no cookie and makes no network request", async () => {
  const calls = []
  const patched = [[http, "request"], [http, "get"], [https, "request"], [https, "get"], [net, "connect"], [net, "createConnection"], [globalThis, "fetch"]]
  const saved = patched.map(([owner, name]) => owner[name])
  patched.forEach(([owner, name]) => { owner[name] = (...args) => { calls.push(name); throw new Error("no network") } })
  const res = fakeResponse()
  try {
    const botscent = { inspect: async () => ({ type: "human", reasons: [] }), VERSION: "1.2.0" }
    await new Promise((done) => mount({ botscent })(fakeRequest(), res, done))
    res.writeHead(200, { "Content-Type": "text/html" })
  } finally {
    patched.forEach(([owner, name], n) => { owner[name] = saved[n] })
  }
  assert.deepEqual(calls, [])
  assert.ok(tokenIn(res.written["server-timing"]), "the token was set")
  assert.equal(res.written["set-cookie"], undefined)
})

test("the secret never appears in a token, a header or a warning", async () => {
  const warnings = []
  cakeExpress({ secret: SECRET.slice(0, fixed.min_secret_bytes - 1), warn: (line) => warnings.push(line) })
  assert.ok(warnings.length === 1 && !warnings[0].includes(SECRET.slice(0, 8)))
  await withServer(mount(), page, async (origin) => {
    const res = await send(origin, "/")
    const everything = res.raw.join("\n")
    const token = tokenIn(res.headers["server-timing"])
    const decoded = Buffer.from(token.split(".")[1], "base64url").toString("utf8")
    for (const text of [everything, decoded]) assert.ok(!text.includes(SECRET) && !text.includes(Buffer.from(SECRET).toString("base64url")))
  })
})

// A request and response just real enough for the middleware: no socket, so no network either.
function fakeRequest() {
  const lines = CHROME_PAGE.flatMap(([name, value]) => [name, value])
  const headers = Object.fromEntries(CHROME_PAGE.map(([name, value]) => [name.toLowerCase(), value]))
  return { method: "GET", url: "/", rawHeaders: lines, headers }
}

function fakeResponse() {
  const set = {}
  return {
    headersSent: false,
    written: null,
    getHeader: (name) => set[name.toLowerCase()],
    setHeader: (name, value) => { set[name.toLowerCase()] = value },
    removeHeader: (name) => { delete set[name.toLowerCase()] },
    writeHead(status, headers) {
      this.written = { ...set, ...Object.fromEntries(Object.entries(headers || {}).map(([k, v]) => [k.toLowerCase(), v])) }
      this.headersSent = true
      return this
    },
  }
}
