"use strict"
/*
 * readme.test.js — the README is what a site owner (or their coding agent) reads before mounting the middleware, and
 * what the token holds is readable by any script on the page: so the README must name every field of the token, every
 * mounting and the caching choice, and say what the token never holds.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const { mintToken } = require("..")
const { SECRET, NOW, CLIENT_IP, plainRequest, payloadOf } = require("./helpers")

const README = fs.readFileSync(path.join(__dirname, "..", "README.md"), "utf8")
const PACKAGE = require("../package.json")

test("the README names every field of the token in its table", async () => {
  const payload = payloadOf(await mintToken(SECRET, plainRequest("/"), { nowMs: NOW, id: "id-1", ip: CLIENT_IP }))
  for (const field of Object.keys(payload)) assert.match(README, new RegExp(`^\\| \`${field}\` \\|`, "m"), field)
})

test("the README shows the three mountings, by the entry points package.json exports", () => {
  for (const entry of ["./express", "./next", "./hono"]) {
    assert.ok(PACKAGE.exports[entry], `package.json exports ${entry}`)
    assert.ok(README.includes(`${PACKAGE.name}/${entry.slice(2)}`), `the README imports ${entry}`)
  }
})

test("the README explains noStore and the 304, and what the token never holds", () => {
  const prose = README.replace(/\s+/g, " ")
  assert.match(prose, /noStore/)
  assert.match(prose, /304/)
  assert.match(prose, /never holds an IP address/i)
  assert.match(prose, /no cookie/i)
})
