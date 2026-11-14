// An animated PNG (APNG: https://wiki.mozilla.org/APNG_Specification) made from screenshots, for README's animated
// demo. Every current browser plays one, GitHub shows it like any picture, and a viewer that
// does not animate PNG shows its first frame. Each frame after the first is only the rectangle that changed since the
// frame before, drawn over it at its place (dispose none, blend source), and a frame the same as the one before only
// lengthens that one: a page that stands still costs one frame however long it is shown. pngjs (already a dependency
// of the screenshots) writes each rectangle's pixels; node:zlib computes the chunks' CRCs.
//   apng([{ rgba, delay }], width, height) -> the file (a Buffer); rgba: width x height x 4 bytes, delay in ms
import { crc32 } from "node:zlib"
import { PNG } from "pngjs"

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]) // protocol: the PNG signature
const DELAY_DEN = 1000 // protocol: an fcTL delay is delay_num / delay_den seconds; ours are milliseconds
const MAX_DELAY = 0xffff // protocol: delay_num is 16 bits
const DISPOSE_NONE = 0, BLEND_SOURCE = 0, LOOP_FOREVER = 0 // protocol: fcTL dispose_op and blend_op, acTL num_plays
const RGB = 2 // protocol: PNG colour type 2; screenshots are opaque, so alpha would only take room
const CHUNK_HEAD = 8, CHUNK_CRC = 4 // protocol: length and type before the data, the CRC after it
const FCTL_TAIL = 6 // protocol: fcTL's delay_num, delay_den (16 bits each), dispose_op and blend_op (8 bits each)

/** The chunks of a PNG file, in order: [{ type, data }]. */
export function chunks(file) {
  const found = []
  for (let at = SIGNATURE.length; at < file.length;) {
    const length = file.readUInt32BE(at)
    found.push({ type: file.toString("latin1", at + 4, at + CHUNK_HEAD), data: file.subarray(at + CHUNK_HEAD, at + CHUNK_HEAD + length) })
    at += CHUNK_HEAD + length + CHUNK_CRC
  }
  return found
}

function chunk(type, data) {
  const head = Buffer.alloc(CHUNK_HEAD)
  head.writeUInt32BE(data.length, 0)
  head.write(type, 4, "latin1")
  const crc = Buffer.alloc(CHUNK_CRC)
  crc.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])) >>> 0, 0)
  return Buffer.concat([head, data, crc])
}

const u32s = (...values) => {
  const out = Buffer.alloc(4 * values.length)
  values.forEach((value, n) => out.writeUInt32BE(value, 4 * n))
  return out
}

/** The smallest rectangle { x, y, width, height } where two frames differ, or null when they are the same. */
export function changed(before, after, width, height) {
  let left = width, top = height, right = -1, bottom = -1
  for (let y = 0; y < height; y++) {
    const row = y * width * 4
    for (let x = 0; x < width; x++) {
      const at = row + x * 4
      if (before[at] !== after[at] || before[at + 1] !== after[at + 1] || before[at + 2] !== after[at + 2]) {
        if (x < left) left = x
        if (x > right) right = x
        if (y < top) top = y
        bottom = y
      }
    }
  }
  return right < 0 ? null : { x: left, y: top, width: right - left + 1, height: bottom - top + 1 }
}

function crop(rgba, width, { x, y, width: w, height: h }) {
  const out = Buffer.alloc(w * h * 4)
  for (let row = 0; row < h; row++) rgba.copy(out, row * w * 4, ((y + row) * width + x) * 4, ((y + row) * width + x + w) * 4)
  return out
}

/** The compressed image data (the IDAT chunks' data, in order) of an RGB PNG of these pixels. */
function imageData(rgba, width, height) {
  const png = new PNG({ width, height })
  png.data = rgba
  const found = chunks(PNG.sync.write(png, { colorType: RGB, inputHasAlpha: true, deflateLevel: 9 }))
  return { header: found.find((c) => c.type === "IHDR").data, idat: found.filter((c) => c.type === "IDAT").map((c) => c.data) }
}

/** Frames as the file will hold them: each the rectangle that changed and how long it shows. */
function parts(frames, width, height) {
  const out = [{ rect: { x: 0, y: 0, width, height }, rgba: frames[0].rgba, delay: frames[0].delay }]
  for (let n = 1; n < frames.length; n++) {
    const rect = changed(frames[n - 1].rgba, frames[n].rgba, width, height)
    if (rect) out.push({ rect, rgba: crop(frames[n].rgba, width, rect), delay: frames[n].delay })
    else out[out.length - 1].delay += frames[n].delay
  }
  return out
}

export function apng(frames, width, height) {
  if (!frames.length) throw new Error("an animation needs at least one frame")
  const shown = parts(frames, width, height)
  const files = [SIGNATURE]
  let sequence = 0
  shown.forEach(({ rect, rgba, delay }, n) => {
    const { header, idat } = imageData(rgba, rect.width, rect.height)
    if (n === 0) files.push(chunk("IHDR", header), chunk("acTL", u32s(shown.length, LOOP_FOREVER)))
    const control = Buffer.concat([u32s(sequence++, rect.width, rect.height, rect.x, rect.y), Buffer.alloc(FCTL_TAIL)])
    control.writeUInt16BE(Math.min(Math.round(delay), MAX_DELAY), 20)
    control.writeUInt16BE(DELAY_DEN, 22)
    control.writeUInt8(DISPOSE_NONE, 24)
    control.writeUInt8(BLEND_SOURCE, 25)
    files.push(chunk("fcTL", control))
    for (const data of idat) files.push(n === 0 ? chunk("IDAT", data) : chunk("fdAT", Buffer.concat([u32s(sequence++), data])))
  })
  files.push(chunk("IEND", Buffer.alloc(0)))
  return Buffer.concat(files)
}
