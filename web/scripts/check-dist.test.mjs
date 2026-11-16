// Tests for check:dist: a built folder with a sample session in it fails; a clean one passes.
// Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { after, test } from "node:test"
import { CONTRACT } from "./check-schemas.mjs"
import { findSamples, sampleMarks } from "./check-dist.mjs"

const dirs = []
after(() => dirs.forEach((d) => rmSync(d, { recursive: true, force: true })))
function dist(files) {
  const dir = mkdtempSync(path.join(tmpdir(), "cake-dist-"))
  dirs.push(dir)
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, name)), { recursive: true })
    writeFileSync(path.join(dir, name), text)
  }
  return dir
}

test("the marks are every sample session id and the sample sessions' sentences", () => {
  const marks = sampleMarks(CONTRACT.fixtureDir)
  for (const mark of ["7f3a-c1", "a91e-07", "90d4-7b", "A human, then Claude in Chrome, then the human again", "6e0f-13", "Codex in-app browser, the whole way"]) {
    assert.ok(marks.includes(mark), mark)
  }
  assert.ok(!marks.includes("Select size M"), "short strings could be ordinary interface text")
  assert.ok(!marks.some((m) => m.includes("Demo shop that comes with cake")), "the recorded shop's own words are not marks")
})

test("a clean build passes", () => {
  assert.deepEqual(findSamples(dist({ "index.html": "<div id=root></div>", "assets/app.js": 'fetch("api/overview")' }), CONTRACT.fixtureDir), [])
})

test("a sample id, a sample sentence or a copied fixture fails", () => {
  const problems = findSamples(dist({
    "assets/app.js": 'const s={id:"7f3a-c1"}',
    "assets/more.js": "title:`A human, then Claude in Chrome, then the human again`",
    "fixtures/setup.json": "{}",
  }), CONTRACT.fixtureDir)
  assert.ok(problems.some((p) => p.startsWith(`assets${path.sep}app.js`) && p.includes("7f3a-c1")), problems.join("\n"))
  assert.ok(problems.some((p) => p.startsWith(`assets${path.sep}more.js`)), problems.join("\n"))
  assert.ok(problems.some((p) => p.includes("copied from src/data")), problems.join("\n"))
})
