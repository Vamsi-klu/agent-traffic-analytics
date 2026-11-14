// The animated PNG writer (scripts/apng.mjs): the changed rectangle between frames, frames that change nothing
// folded into the one before, and a file laid out as the APNG specification says, whose first frame any PNG reader
// reads. Usage: node --test scripts/
import assert from "node:assert/strict"
import { test } from "node:test"
import { PNG } from "pngjs"
import { apng, changed, chunks } from "./apng.mjs"

const W = 6, H = 4
/** An opaque frame of one colour, with some pixels painted another: [[x, y, [r, g, b]]]. */
function frame(base, painted = []) {
  const rgba = Buffer.alloc(W * H * 4)
  for (let n = 0; n < W * H; n++) rgba.set([...base, 255], n * 4)
  for (const [x, y, colour] of painted) rgba.set([...colour, 255], (y * W + x) * 4)
  return rgba
}
const WHITE = [255, 255, 255], INK = [43, 33, 24], PINK = [255, 92, 138]

test("the changed rectangle bounds every pixel that differs, and the same frame has none", () => {
  const before = frame(WHITE)
  assert.equal(changed(before, frame(WHITE), W, H), null)
  assert.deepEqual(changed(before, frame(WHITE, [[1, 1, INK], [3, 2, PINK]]), W, H), { x: 1, y: 1, width: 3, height: 2 })
})

test("a file of the frames that change: the first whole, then each changed rectangle at its place", () => {
  const frames = [{ rgba: frame(WHITE), delay: 500 }, { rgba: frame(WHITE), delay: 700 },
    { rgba: frame(WHITE, [[4, 3, INK]]), delay: 300 }]
  const file = apng(frames, W, H)
  const found = chunks(file)
  assert.deepEqual(found.map((c) => c.type), ["IHDR", "acTL", "fcTL", "IDAT", "fcTL", "fdAT", "IEND"])
  assert.equal(found[1].data.readUInt32BE(0), 2, "two frames: the second, the same as the first, only lengthens it")
  const [first, second] = found.filter((c) => c.type === "fcTL").map((c) => c.data)
  assert.deepEqual([first.readUInt32BE(4), first.readUInt32BE(8), first.readUInt16BE(20), first.readUInt16BE(22)], [W, H, 1200, 1000])
  assert.deepEqual([second.readUInt32BE(4), second.readUInt32BE(8), second.readUInt32BE(12), second.readUInt32BE(16)], [1, 1, 4, 3])
  const sequence = [first.readUInt32BE(0), second.readUInt32BE(0), found[5].data.readUInt32BE(0)]
  assert.deepEqual(sequence, [0, 1, 2], "fcTL and fdAT share one sequence, from 0")
})

test("any PNG reader reads the first frame", () => {
  const first = frame(WHITE, [[0, 0, PINK]])
  const png = PNG.sync.read(apng([{ rgba: first, delay: 100 }, { rgba: frame(INK), delay: 100 }], W, H))
  assert.deepEqual([png.width, png.height], [W, H])
  assert.deepEqual(Buffer.from(png.data), first)
})
