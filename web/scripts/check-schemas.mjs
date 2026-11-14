// check:schemas (run by `npm run check:ui`): the /api contract stays one contract (S5.1).
//  1. Every schema in src/data/schema/ uses only the keywords scripts/json-schema.mjs knows (so the Python half can
//     check cake's answers the same way), closes its objects, and has no broken $ref.
//  2. Every sample in src/data/fixtures/ matches the schema of the same name, and every schema but common has a sample.
//     A schema's samples are fixtures/<name>.json and every .json under fixtures/<name>/ (more sessions in session/,
//     their replay chunks in replay/<id>/, S5.4), and fixtures/library/<name>.json (cake's answers on the fixed test
//     library, S5.3).
//  3. Every sample also type-checks as the TypeScript type its schema's "title" names in src/data/types.ts, so the
//     pages and the schemas cannot drift apart.
// Usage: node scripts/check-schemas.mjs   (exit 1 on any problem)
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import ts from "typescript"
import { LIBRARY } from "./fixture-api.mjs"
import { checkSchema, loadSchemas, validate } from "./json-schema.mjs"

const SHARED = "common.schema.json"
const data = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "data")
export const CONTRACT = { schemaDir: path.join(data, "schema"), fixtureDir: path.join(data, "fixtures"), typesFile: path.join(data, "types.ts") }

/** Every problem with the contract in these folders; empty when schemas, samples and types agree. */
export function checkContract({ schemaDir, fixtureDir, typesFile }) {
  const problems = []
  const schemas = loadSchemas(schemaDir)
  for (const file of schemas.keys()) problems.push(...checkSchema(file, schemas))

  const fixtures = sampleFiles(fixtureDir).map((rel) => {
    const name = rel.slice(0, -".json".length), [first, second] = name.split("/")
    const endpoint = first === LIBRARY ? second : first
    return { name, file: `${endpoint}.schema.json`, value: JSON.parse(readFileSync(path.join(fixtureDir, rel), "utf8")) }
  })
  for (const file of schemas.keys()) if (file !== SHARED && !fixtures.some((f) => f.file === file)) problems.push(`${file}: no sample in fixtures/`)
  for (const { name, file, value } of fixtures) {
    const schema = schemas.get(file)
    if (!schema) { problems.push(`fixtures/${name}.json: no schema/${file}`); continue }
    if (!schema.title) problems.push(`${file}: no "title" naming its type in types.ts`)
    for (const p of validate(value, schema, file, schemas)) problems.push(`fixtures/${name}.json ${p}`)
  }
  const typed = fixtures.filter((f) => schemas.get(f.file)?.title).map((f) => ({ ...f, type: schemas.get(f.file).title }))
  problems.push(...typeCheck(typed, typesFile))
  return { problems, schemas: schemas.size, samples: fixtures.length }
}

/** Every .json under the fixtures folder, as a path relative to it with / separators. */
export function sampleFiles(dir, prefix = "") {
  return readdirSync(path.join(dir, prefix)).sort().flatMap((name) => {
    const rel = prefix ? `${prefix}/${name}` : name
    if (statSync(path.join(dir, rel)).isDirectory()) return sampleFiles(dir, rel)
    return name.endsWith(".json") ? [rel] : []
  })
}

/** Each sample becomes an object literal typed as its type, so tsc applies the literal unions and excess-property
 *  checks a JSON import would not. */
function typeCheck(samples, typesFile) {
  const tmp = mkdtempSync(path.join(tmpdir(), "cake-fixtures-"))
  try {
    const source = path.join(tmp, "fixtures-check.ts")
    let text = `import type * as T from ${JSON.stringify(typesFile.replace(/\.ts$/, ""))}\n`
    const starts = [] // [first line (0-based), sample name], in order
    for (const s of samples) {
      starts.push([text.split("\n").length - 1, s.name])
      text += `export const ${s.name.replace(/\W/g, "_")}: T.${s.type} = ${JSON.stringify(s.value, null, 1)}\n`
    }
    writeFileSync(source, text)
    const program = ts.createProgram([source], {
      strict: true, noEmit: true, skipLibCheck: true, types: [], target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler,
    })
    return ts.getPreEmitDiagnostics(program).map((d) => {
      const line = d.file && d.file.fileName === source ? d.file.getLineAndCharacterOfPosition(d.start ?? 0).line : -1
      const owner = starts.filter(([start]) => start <= line).at(-1)?.[1]
      return `${owner ? `fixtures/${owner}.json` : path.basename(typesFile)} vs types.ts: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`
    })
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { problems, schemas, samples } = checkContract(CONTRACT)
  if (problems.length) { console.log(`check:schemas FAIL (${problems.length})`); for (const p of problems) console.log("  " + p); process.exit(1) }
  console.log(`check:schemas OK · ${schemas} schemas · ${samples} samples match their schema and src/data/types.ts`)
}
