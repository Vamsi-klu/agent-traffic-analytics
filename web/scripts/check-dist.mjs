// check:dist (runs at the end of `npm run build`): the release shows no sample data. No session from
// src/data/fixtures/ (its id, or a sentence of a sample session) appears in any file of dist/, and nothing in dist/
// comes from the fixtures or schema folders. The fixtures only feed the screenshot and dev servers. The recorded
// replays (fixtures/replay/) are left out of the marks: they are the recorded shop's own pages (tests/site, the demo shop
// until 0.4.0), whose words are not the interface's.
// Usage: node scripts/check-dist.mjs   (exit 1 on any problem)
import { readdirSync, readFileSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { sampleFiles } from "./check-schemas.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const MIN_SENTENCE = 24 // shorter strings ("Select size M") could be ordinary interface text

const walk = (dir) => readdirSync(dir).flatMap((n) => { const p = path.join(dir, n); return statSync(p).isDirectory() ? walk(p) : [p] })

/** What gives a sample session away: every session id in the fixtures, and the sample sessions' sentences. */
export function sampleMarks(fixtureDir) {
  const marks = new Set()
  const visit = (value, inSession) => {
    if (Array.isArray(value)) return value.forEach((v) => visit(v, inSession))
    if (typeof value === "string" && inSession && value.length >= MIN_SENTENCE && !value.includes("://")) marks.add(value)
    if (typeof value !== "object" || value === null) return
    if (typeof value.id === "string" && typeof value.verdict === "string") marks.add(value.id)
    Object.values(value).forEach((v) => visit(v, inSession))
  }
  for (const file of sampleFiles(fixtureDir).filter((f) => !f.startsWith("replay/"))) {
    visit(JSON.parse(readFileSync(path.join(fixtureDir, file), "utf8")), file === "session.json" || file.startsWith("session/"))
  }
  return [...marks]
}

/** Every place a sample shows up in a built folder. */
export function findSamples(distDir, fixtureDir) {
  const marks = sampleMarks(fixtureDir)
  const problems = []
  for (const file of walk(distDir)) {
    const rel = path.relative(distDir, file)
    if (/(^|[\\/])(fixtures|schema)([\\/]|$)|\.schema\.json$/.test(rel)) problems.push(`${rel}: copied from src/data`)
    const text = readFileSync(file, "latin1") // byte-for-byte, so binary files can't throw
    for (const mark of marks) if (text.includes(Buffer.from(mark, "utf8").toString("latin1"))) problems.push(`${rel}: contains sample data "${mark}"`)
  }
  return problems
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dist = path.join(web, "dist"), fixtures = path.join(web, "src", "data", "fixtures")
  const problems = findSamples(dist, fixtures)
  if (problems.length) { console.log(`check:dist FAIL (${problems.length})`); for (const p of problems) console.log("  " + p); process.exit(1) }
  console.log(`check:dist OK · no sample session in dist/ (${sampleMarks(fixtures).length} ids and sentences looked for)`)
}
