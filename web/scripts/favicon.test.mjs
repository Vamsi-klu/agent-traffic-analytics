// The favicon (scripts/favicon.mjs): the .ico packing reads back as written, the committed public/favicon.ico holds
// Crumb's head at each size, the pages link it, and a committed file that is not what the pages draw is out of date
// (npm run visual draws it and fails on that). Usage: node --test scripts/
import assert from "node:assert/strict"
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { test } from "node:test"
import { FAVICON, SIZES, ico, readIco, staleFavicon } from "./favicon.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
/** Width and height from a PNG's IHDR chunk (right after the 8-byte signature and the chunk's length and type). */
const pngSize = (png) => [png.readUInt32BE(16), png.readUInt32BE(20)]

test("an .ico holds its PNG images one after the other, each listed with its size and place", () => {
  const images = [{ size: 16, png: Buffer.from("sixteen") }, { size: 256, png: Buffer.from("two hundred fifty-six") }]
  const file = ico(images)
  assert.deepEqual([file.readUInt16LE(0), file.readUInt16LE(2), file.readUInt16LE(4)], [0, 1, 2])
  assert.equal(file.readUInt8(6 + 16), 0, "256 is written as 0")
  assert.deepEqual(readIco(file).map(({ size, png }) => [size, png.toString()]), images.map(({ size, png }) => [size, png.toString()]))
})

test("public/favicon.ico is one PNG for each size, that many pixels square", () => {
  const images = readIco(readFileSync(FAVICON))
  assert.deepEqual(images.map((image) => image.size), SIZES)
  for (const { size, png } of images) {
    assert.deepEqual(png.subarray(0, PNG_SIGNATURE.length), PNG_SIGNATURE, `${size}: a PNG`)
    assert.deepEqual(pngSize(png), [size, size])
  }
})

test("the pages link it, so the browser asks for it wherever the pages are served", () => {
  assert.match(readFileSync(path.join(web, "index.html"), "utf8"), /<link rel="icon" href="\/favicon\.ico"/)
})

/** A scratch folder for one test, removed afterwards. */
function scratch(t) {
  const dir = mkdtempSync(path.join(tmpdir(), "cake-favicon-"))
  t.after(() => rmSync(dir, { recursive: true, force: true }))
  return dir
}

test("a committed favicon is out of date unless it is byte for byte what the pages draw", (t) => {
  const file = path.join(scratch(t), "favicon.ico")
  writeFileSync(file, Buffer.from("as drawn"))
  assert.deepEqual(staleFavicon(Buffer.from("as drawn"), file), [])
  assert.match(staleFavicon(Buffer.from("drawn after the tokens changed"), file).join(), /is not what scripts\/favicon\.mjs draws/)
})

test("a favicon that is not there is missing", (t) => {
  assert.match(staleFavicon(Buffer.from("as drawn"), path.join(scratch(t), "favicon.ico")).join(), /is missing/)
})
