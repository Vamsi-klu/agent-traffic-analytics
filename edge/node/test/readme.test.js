"use strict"
/*
 * readme.test.js — the README is what a site owner (or their coding agent) reads before mounting the middleware, and
 * what the token holds is readable by any script on the page: so the README must name every field of the token, every
 * mounting and the caching choice, say what the token never holds, and install the package from its copy in the site
 * (the folder agentcake/data/frameworks.json names), never from AgentCake's own folder, which a CI server lacks.
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

test("the README installs the package from its copy in the site, the folder setup --print --site names", () => {
  const frameworks = require(path.join(__dirname, "..", "..", "..", "agentcake", "data", "frameworks.json"))
  const folders = new Set(frameworks.frameworks.map((each) => (each.middleware || {}).folder).filter(Boolean))
  assert.equal(folders.size, 1, "one folder for every Node mounting")
  const [folder] = folders
  assert.ok(README.includes(`npm install ./${folder}`), "installed by a relative path")
  assert.ok(README.includes(`"${PACKAGE.name}": "file:${folder}"`), "what package.json then lists")
  assert.doesNotMatch(README, /npm install <edge folder>/, "never from AgentCake's own folder")
})

test("the README explains noStore and the 304, and what the token never holds", () => {
  const prose = README.replace(/\s+/g, " ")
  assert.match(prose, /noStore/)
  assert.match(prose, /304/)
  assert.match(prose, /never holds an IP address/i)
  assert.match(prose, /no cookie/i)
})
