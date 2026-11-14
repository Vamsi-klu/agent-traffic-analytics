"use strict"
/*
 * test-site.js — a small site for trying the middleware in a real browser: a home page and a second page that link to
 * each other, served by node:http with the Express mounting. No dependencies.
 *
 *   CAKE_SERVER_TIMING_SECRET=<secret> node edge/node/scripts/test-site.js [--port 8123] [--no-store]
 *
 * Each page shows what its own navigation entry carries in Server-Timing (what cake.js reads): the token's id and the
 * four Sec-Fetch values inside it. Pages go out with Cache-Control: no-cache and an ETag, so opening one again is a 304,
 * unless --no-store turns on the middleware's noStore. browser-check.mjs starts it in-process with startSite();
 * tests/browser/token_revisits.mjs too, with cake.js on every page (`head`) and each answer logged (`onResponse`).
 * Steps S4.1, S4.2.
 */
const crypto = require("node:crypto")
const http = require("node:http")
const { cakeExpress } = require("../express")

const PAGES = {
  "/": { title: "Test shop", link: "/next", label: "Next page" },
  "/next": { title: "Second page", link: "/", label: "Home" },
}

// The page reads its own navigation entry, as cake.js does, and shows the token's id and Sec-Fetch values.
const READER = `
const entry = performance.getEntriesByType("navigation")[0]
const cake = (entry.serverTiming || []).find((each) => each.name === "cake")
const out = document.getElementById("cake")
if (!cake) out.textContent = "No cake entry in this page's Server-Timing."
else {
  const body = atob(cake.description.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
  const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(body, (char) => char.charCodeAt(0))))
  out.textContent = "token " + payload.id + " · Sec-Fetch site " + payload.sf.s + ", mode " + payload.sf.m + ", dest " + payload.sf.d + ", user " + payload.sf.u
}`

function html(page, head) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${page.title}</title>${head}</head>
<body><h1>${page.title}</h1><p><a id="link" href="${page.link}">${page.label}</a></p><p id="cake"></p>
<script>${READER}</script></body></html>`
}

function handler(req, res, head) {
  const path = (req.url || "/").split("?")[0]
  const page = PAGES[path]
  if (!page) {
    res.writeHead(404, { "Content-Type": "text/plain" }) // protocol: not found
    res.end("not found")
    return
  }
  const body = html(page, head)
  const etag = `"${crypto.createHash("sha256").update(body).digest("base64url")}"`
  res.setHeader("Cache-Control", "no-cache")
  res.setHeader("ETag", etag)
  if (req.headers["if-none-match"] === etag) {
    res.statusCode = 304 // protocol: not modified
    res.end()
    return
  }
  res.setHeader("Content-Type", "text/html; charset=utf-8")
  res.end(body)
}

// { url, close } for a site on 127.0.0.1 at `port` (0: any free port). head: more HTML for each page's head (the
// cake.js line); onResponse({ path, status, serverTiming }): called once each answer has gone out.
function startSite({ secret, port = 0, noStore = false, head = "", onResponse = null } = {}) {
  const cake = cakeExpress({ secret, noStore, clientIp: (req) => req.socket.remoteAddress })
  const server = http.createServer((req, res) => {
    if (onResponse) {
      res.on("finish", () => onResponse({ path: req.url, status: res.statusCode, serverTiming: res.getHeader("server-timing") || null }))
    }
    cake(req, res, () => handler(req, res, head))
  })
  return new Promise((resolve) => {
    server.listen(port, "127.0.0.1", () => {
      resolve({ url: `http://127.0.0.1:${server.address().port}/`, enabled: cake.enabled, close: () => new Promise((done) => server.close(done)) })
    })
  })
}

if (require.main === module) {
  const args = process.argv.slice(2)
  const at = args.indexOf("--port")
  startSite({ port: at === -1 ? 0 : Number(args[at + 1]), noStore: args.includes("--no-store") }).then((site) => {
    console.log(`${site.url}${site.enabled ? "" : "  (no secret: pages carry no token)"}`)
  })
}

module.exports = { startSite }
