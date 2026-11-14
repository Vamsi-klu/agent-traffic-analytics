"use strict"
/*
 * latency.js — what the middleware adds to a page's response time. Two servers in this process serve the same
 * small page, one through the Express mounting and one without; a keep-alive client asks them in turn with the header
 * lines of a Chrome navigation, so the middleware does all its work on every request, and the two sides' p50, p90 and
 * p99 are compared. Node's own clock (process.hrtime), no load-testing tool. The Web Crypto path (the Next.js mounting)
 * is timed on its own too, as calls in this process.
 *
 *   node edge/node/scripts/latency.js --requests 1000 --max-p50-diff-ms 5 [--out latency.json]
 *
 * Exit status 1 when the p50 difference is over the limit.
 */
const crypto = require("node:crypto")
const fs = require("node:fs")
const http = require("node:http")
const { cakeExpress } = require("../express")
const { cakeNext } = require("../next")

const SECRET_BYTES = 32
const WARM_UP_SHARE = 0.1 // the first tenth of the requests again, unmeasured, before measuring
const PERCENTILES = { p50: 0.5, p90: 0.9, p99: 0.99 }
const NS_PER_MS = 1e6
const CHROME = [
  ["Connection", "keep-alive"],
  ["sec-ch-ua", '"Chromium";v="149", "Google Chrome";v="149"'],
  ["sec-ch-ua-mobile", "?0"],
  ["sec-ch-ua-platform", '"macOS"'],
  ["User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"],
  ["Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"],
  ["Sec-Fetch-Site", "same-origin"],
  ["Sec-Fetch-Mode", "navigate"],
  ["Sec-Fetch-User", "?1"],
  ["Sec-Fetch-Dest", "document"],
  ["Accept-Language", "en-US,en;q=0.9"],
]
const PAGE = "<!doctype html><title>Shop</title><h1>Shop</h1>"

function required(name) {
  const at = process.argv.indexOf(name)
  const value = at === -1 ? NaN : Number(process.argv[at + 1])
  if (!Number.isFinite(value)) throw new Error(`${name} <number> is required`)
  return value
}

function page(req, res) {
  res.setHeader("Content-Type", "text/html; charset=utf-8")
  res.end(PAGE)
}

function listen(handler) {
  const server = http.createServer(handler)
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)))
}

// One request's time in milliseconds, from sending it to the end of the response.
function timeOne(agent, port) {
  return new Promise((resolve, reject) => {
    const started = process.hrtime.bigint()
    const headers = [["Host", `127.0.0.1:${port}`], ...CHROME].flat()
    const request = http.request({ host: "127.0.0.1", port, path: "/", headers, agent }, (res) => {
      res.resume()
      res.on("end", () => resolve(Number(process.hrtime.bigint() - started) / NS_PER_MS))
    })
    request.on("error", reject)
    request.end()
  })
}

function summary(times) {
  const sorted = [...times].sort((a, b) => a - b)
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.ceil(q * sorted.length) - 1)]
  return Object.fromEntries(Object.entries(PERCENTILES).map(([name, q]) => [name, Number(at(q).toFixed(4))]))
}

async function overHttp(requests, secret) {
  const plain = await listen(page)
  const cake = cakeExpress({ secret, clientIp: (req) => req.socket.remoteAddress })
  const withCake = await listen((req, res) => cake(req, res, () => page(req, res)))
  const agents = { plain: new http.Agent({ keepAlive: true, maxSockets: 1 }), cake: new http.Agent({ keepAlive: true, maxSockets: 1 }) }
  const ports = { plain: plain.address().port, cake: withCake.address().port }
  const times = { plain: [], cake: [] }
  try {
    const warmUp = Math.ceil(requests * WARM_UP_SHARE)
    for (let i = 0; i < warmUp; i++) for (const side of ["plain", "cake"]) await timeOne(agents[side], ports[side])
    for (let i = 0; i < requests; i++) {
      const order = i % 2 ? ["plain", "cake"] : ["cake", "plain"] // alternate, so drift falls on both sides alike
      for (const side of order) times[side].push(await timeOne(agents[side], ports[side]))
    }
  } finally {
    Object.values(agents).forEach((agent) => agent.destroy())
    await Promise.all([plain, withCake].map((server) => new Promise((done) => server.close(done))))
  }
  return { plain: summary(times.plain), cake: summary(times.cake) }
}

async function webCryptoCalls(requests, secret) {
  const cake = cakeNext({ secret })
  const times = []
  const headers = [["Host", "shop.example"], ...CHROME]
  for (let i = 0; i < requests; i++) {
    const request = new Request("https://shop.example/", { headers })
    const started = process.hrtime.bigint()
    await cake(request, new Response(null))
    times.push(Number(process.hrtime.bigint() - started) / NS_PER_MS)
  }
  return summary(times)
}

async function main() {
  const requests = required("--requests")
  const limit = required("--max-p50-diff-ms")
  const secret = crypto.randomBytes(SECRET_BYTES).toString("base64url") // a fresh test secret, never written down
  const http1 = await overHttp(requests, secret)
  const added = Number((http1.cake.p50 - http1.plain.p50).toFixed(4))
  const result = {
    node: process.version,
    requests,
    over_http_ms: http1,
    p50_added_ms: added,
    limit_ms: limit,
    within_limit: added <= limit,
    web_crypto_call_ms: await webCryptoCalls(requests, secret),
  }
  const at = process.argv.indexOf("--out")
  if (at !== -1) fs.writeFileSync(process.argv[at + 1], `${JSON.stringify(result, null, 2)}\n`)
  console.log(JSON.stringify(result, null, 2))
  process.exitCode = result.within_limit ? 0 : 1
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
