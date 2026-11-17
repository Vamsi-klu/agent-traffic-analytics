// Tests for the files Tailwind reads (scripts/tailwind-sources.mjs, a check:ui rule): left to itself it reads a script's
// and a test's words too; with source(none) and the code's own @source, only the pages' .ts and .tsx.
// Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { after, test } from "node:test"
import { fileURLToPath } from "node:url"
import { notPageCode, tailwindFiles } from "./tailwind-sources.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const dirs = []
after(() => dirs.forEach((d) => rmSync(d, { recursive: true, force: true })))

/** A web/ folder in miniature with this stylesheet: pages' code, a sample answer and a licence text in src, a script and
 *  a test beside it (the packages are web/'s, for the stylesheet's @import). */
function project(stylesheet) {
  const dir = realpathSync(mkdtempSync(path.join(tmpdir(), "cake-sources-"))) // the scanner gives real paths
  dirs.push(dir)
  symlinkSync(path.join(web, "node_modules"), path.join(dir, "node_modules"))
  const files = {
    "src/index.css": stylesheet,
    "src/main.tsx": 'export const App = () => <p className="flex">x</p>',
    "src/lib/words.ts": 'export const WORDS = { title: "Sessions" }',
    "src/data/fixtures/sample.json": '{ "title": "blur" }',
    "src/assets/fonts/OFL.txt": "table of contents",
    "scripts/shots.mjs": "// a blur in a comment",
    "tests/page.test.mjs": 'probe.className = "bg-agent-foreground"',
  }
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, name)), { recursive: true })
    writeFileSync(path.join(dir, name), text)
  }
  return dir
}

const relative = (dir, files) => files.map((f) => path.relative(dir, f).split(path.sep).join("/")).sort()

test("left to itself, Tailwind reads every file of the folder: scripts, tests, samples and texts are not the pages' code", async () => {
  const dir = project('@import "tailwindcss";\n')
  const files = await tailwindFiles(path.join(dir, "src/index.css"), dir)
  assert.deepEqual(relative(dir, notPageCode(files, path.join(dir, "src"))),
    ["scripts/shots.mjs", "src/assets/fonts/OFL.txt", "src/data/fixtures/sample.json", "src/index.css", "tests/page.test.mjs"])
})

test("with source(none) and @source for the code, Tailwind reads only the pages' .ts and .tsx", async () => {
  const dir = project('@import "tailwindcss" source(none);\n@source "./**/*.{ts,tsx}";\n')
  const files = await tailwindFiles(path.join(dir, "src/index.css"), dir)
  assert.deepEqual(relative(dir, files), ["src/lib/words.ts", "src/main.tsx"])
  assert.deepEqual(notPageCode(files, path.join(dir, "src")), [])
})
