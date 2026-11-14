"use strict"
/*
 * helpers.js — what the tests share: a test-only secret and clock, a browser's page request as header lines, those
 * lines as a Fetch Request or a plain request, a token's payload read without checking its MAC, and a small HTTP
 * server and client that keep header lines in the order given.
 *
 * Node's test runner loads every file under test/, this one included; it defines no test of its own.
 */
const http = require("node:http")

const SECRET = "test-only secret, never used outside these tests"
const OTHER_SECRET = "another test-only secret, also never used outside"
const NOW = Date.UTC(2026, 10, 12, 17, 0, 0)
const CLIENT_IP = "203.0.113.77" // RFC 5737 documentation range: nobody's address

// A top-level navigation typed into Chrome on macOS: the header lines in the order Chrome sends them.
const CHROME_PAGE = [
  ["Host", "shop.example"],
  ["Connection", "keep-alive"],
  ["sec-ch-ua", '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'],
  ["sec-ch-ua-mobile", "?0"],
  ["sec-ch-ua-platform", '"macOS"'],
  ["Upgrade-Insecure-Requests", "1"],
  ["User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"],
  ["Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"],
  ["Sec-Fetch-Site", "none"],
  ["Sec-Fetch-Mode", "navigate"],
  ["Sec-Fetch-User", "?1"],
  ["Sec-Fetch-Dest", "document"],
  ["Accept-Encoding", "gzip, deflate, br, zstd"],
  ["Accept-Language", "en-US,en;q=0.9"],
]

// The lines with some changed: a value replaces every line of that name, null removes them, a new name is added last.
function withHeaders(lines, changes) {
  const wanted = new Map(Object.entries(changes).map(([name, value]) => [name.toLowerCase(), value]))
  const out = []
  for (const [name, value] of lines) {
    const key = name.toLowerCase()
    if (!wanted.has(key)) out.push([name, value])
    else if (wanted.get(key) !== null) {
      out.push([name, wanted.get(key)])
      wanted.set(key, undefined)
    }
  }
  for (const [name, value] of wanted) if (value !== undefined && value !== null) out.push([name, value])
  return out
}

function fetchRequest(path, lines = CHROME_PAGE, method = "GET") {
  return new Request(`https://shop.example${path}`, { method, headers: lines })
}

function plainRequest(path, lines = CHROME_PAGE, method = "GET") {
  return { method, path, headers: lines }
}

// The payload as anyone reading the response can read it: no secret needed.
function payloadOf(token) {
  const body = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")
  return JSON.parse(Buffer.from(body, "base64").toString("utf8"))
}

// The token inside a Server-Timing value (`cake;desc="…"`), or null.
function tokenIn(serverTiming) {
  const match = /(?:^|,)\s*cake;desc="([^"]*)"/.exec(serverTiming || "")
  return match ? match[1] : null
}

function listen(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler)
    server.listen(0, "127.0.0.1", () => {
      const origin = `http://127.0.0.1:${server.address().port}`
      resolve({ origin, close: () => new Promise((done) => server.close(done)) })
    })
  })
}

// One request whose header lines go out exactly in the order given.
function send(origin, path, { method = "GET", lines = CHROME_PAGE } = {}) {
  return new Promise((resolve, reject) => {
    const { hostname, port } = new URL(origin) // the path goes out exactly as given, even one starting with "//"
    const flat = lines.flatMap(([name, value]) => [name, value])
    const request = http.request({ host: hostname, port, path, method, headers: flat, agent: false }, (res) => {
      const chunks = []
      res.on("data", (chunk) => chunks.push(chunk))
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, raw: res.rawHeaders, body: Buffer.concat(chunks).toString("utf8") }))
    })
    request.on("error", reject)
    request.end()
  })
}

module.exports = { SECRET, OTHER_SECRET, NOW, CLIENT_IP, CHROME_PAGE, withHeaders, fetchRequest, plainRequest, payloadOf, tokenIn, listen, send }
