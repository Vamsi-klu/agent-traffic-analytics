// Tests for check:schemas and the small JSON Schema validator: the real contract passes, and each way it can
// break is caught. Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { after, test } from "node:test"
import { CONTRACT, checkContract } from "./check-schemas.mjs"
import { loadSchemas, validate } from "./json-schema.mjs"

const copies = []
after(() => copies.forEach((dir) => rmSync(dir, { recursive: true, force: true })))

/** A throwaway copy of the contract, changed by `change(paths)`, then checked. */
function checkChanged(change) {
  const dir = mkdtempSync(path.join(tmpdir(), "cake-contract-"))
  copies.push(dir)
  const paths = { schemaDir: path.join(dir, "schema"), fixtureDir: path.join(dir, "fixtures"), typesFile: path.join(dir, "types.ts") }
  cpSync(CONTRACT.schemaDir, paths.schemaDir, { recursive: true })
  cpSync(CONTRACT.fixtureDir, paths.fixtureDir, { recursive: true })
  cpSync(CONTRACT.typesFile, paths.typesFile)
  change(paths)
  return checkContract(paths).problems
}
const editJson = (file, edit) => { const v = JSON.parse(readFileSync(file, "utf8")); edit(v); writeFileSync(file, JSON.stringify(v)) }
const editText = (file, from, to) => { const s = readFileSync(file, "utf8"); assert.ok(s.includes(from), `${from} not in ${file}`); writeFileSync(file, s.replace(from, to)) }
const has = (problems, ...parts) => assert.ok(problems.some((p) => parts.every((x) => p.includes(x))), `no problem with ${parts.join(" + ")} in:\n${problems.join("\n")}`)

test("the contract in src/data passes", () => {
  assert.deepEqual(checkContract(CONTRACT).problems, [])
})

test("a sample with a value outside an enum fails the schema and the type", () => {
  const problems = checkChanged((p) => editJson(path.join(p.fixtureDir, "overview.json"), (o) => { o.latest_agent[0].verdict = "robot" }))
  has(problems, "fixtures/overview.json $.latest_agent[0].verdict", "not one of")
  has(problems, "fixtures/overview.json vs types.ts", "robot")
})

test("a field the contract doesn't have fails the schema and the type", () => {
  const problems = checkChanged((p) => editJson(path.join(p.fixtureDir, "settings.json"), (s) => { s.theme = "dark" }))
  has(problems, "fixtures/settings.json", '"theme" is not in the contract')
  has(problems, "fixtures/settings.json vs types.ts", "theme")
})

test("a missing required field fails", () => {
  const problems = checkChanged((p) => editJson(path.join(p.fixtureDir, "sessions.json"), (s) => { delete s.page_size }))
  has(problems, "fixtures/sessions.json", '"page_size" is missing')
})

test("a type in types.ts that drifts from its schema fails", () => {
  const problems = checkChanged((p) => editText(p.typesFile, "  page_size: number", "  pageSize: number"))
  has(problems, "fixtures/sessions.json vs types.ts", "page_size")
})

test("a schema keyword the small validators don't know fails", () => {
  const problems = checkChanged((p) => editJson(path.join(p.schemaDir, "setup.schema.json"), (s) => { s.properties.terminal = { type: "string", format: "uri" } }))
  has(problems, "setup.schema.json", 'unknown keyword "format"')
})

test("a broken $ref, an open object and a schema without a sample fail", () => {
  const problems = checkChanged((p) => {
    editJson(path.join(p.schemaDir, "error.schema.json"), (s) => { s.properties.error = { $ref: "common.schema.json#/$defs/Nope" } })
    editJson(path.join(p.schemaDir, "health.schema.json"), (s) => { delete s.properties.space.additionalProperties })
    rmSync(path.join(p.fixtureDir, "replay"), { recursive: true })
  })
  has(problems, "error.schema.json", "points nowhere")
  has(problems, "health.schema.json", "must say additionalProperties")
  has(problems, "replay.schema.json: no sample")
})

test("samples in a folder are checked against the schema the folder is named after", () => {
  const problems = checkChanged((p) => {
    editJson(path.join(p.fixtureDir, "replay", "7f3a-c1", "0.json"), (c) => { c.events[0].type = "meta" })
    editJson(path.join(p.fixtureDir, "session", "2b9e-c4.json"), (d) => { d.replay.missing = "lost" })
  })
  has(problems, "fixtures/replay/7f3a-c1/0.json $.events[0].type", "is not integer")
  has(problems, "fixtures/session/2b9e-c4.json $.replay.missing", "not one of")
  has(problems, "fixtures/session/2b9e-c4.json vs types.ts", "lost")
})

test("the validator applies number and string rules only to their own types", () => {
  const schemas = loadSchemas(CONTRACT.schemaDir)
  const summary = { $ref: "common.schema.json#/$defs/SessionSummary" }
  const row = JSON.parse(readFileSync(path.join(CONTRACT.fixtureDir, "sessions.json"), "utf8")).results[3]
  assert.deepEqual(validate(row, summary, "x.schema.json", schemas), [])
  assert.equal(row.agent, null) // minLength on "agent" does not apply to null
  has(validate({ ...row, agent: "" }, summary, "x.schema.json", schemas), "$.agent", "shorter than 1")
  has(validate({ ...row, pages: 1.5 }, summary, "x.schema.json", schemas), "$.pages", "is not integer")
  has(validate({ ...row, share: { human: 101, agent: 0, unsure: 0 } }, summary, "x.schema.json", schemas), "$.share.human", "above 100")
})
