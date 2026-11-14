// The favicon (S5.2): Crumb's head, the top bar's logo (DESIGN.md §7), as public/favicon.ico, which the build copies
// into dist/ and cake serves at /favicon.ico, where browsers look for it (the local pages).
// The app draws it itself: Chromium opens the built pages in the light theme, copies the logo's SVG with the colours the
// page gives each shape (tokens.css, through the page's own styles) written in, and draws it at each size; the PNGs go
// into one .ico file (PNG images inside an .ico, which every current browser reads).
//   cd web && npm run build && node scripts/favicon.mjs        (when Crumb or the tokens change; commit the file)
// The file is checked: `npm run visual` draws it again from the build it
// screenshots and fails while public/favicon.ico is not what this script would write (staleFavicon). That check runs
// there, not in check:ui, because drawing it takes the built pages and Chromium, which visual has open right after the
// build.
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { existsSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))
export const FAVICON = path.join(here, "..", "public", "favicon.ico")
export const SIZES = [16, 32, 48] // protocol: the sizes browsers and systems take from an .ico (tab, taskbar, shortcut)
const ICONDIR_BYTES = 6, ICONDIRENTRY_BYTES = 16, TYPE_ICON = 1, PLANES = 1, BITS = 32 // protocol: the .ico format
const LOGO = "header a svg.crumb"
/** What the page's styles set on the logo's shapes, written into the copy as SVG attributes. */
const PAINT = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity"]

/** An .ico file holding these PNG images ([{ size, png }]); a size of 256 is written as 0, as the format says. */
export function ico(images) {
  const head = Buffer.alloc(ICONDIR_BYTES)
  head.writeUInt16LE(TYPE_ICON, 2)
  head.writeUInt16LE(images.length, 4)
  let offset = ICONDIR_BYTES + ICONDIRENTRY_BYTES * images.length
  const entries = images.map(({ size, png }) => {
    const entry = Buffer.alloc(ICONDIRENTRY_BYTES)
    entry.writeUInt8(size & 0xff, 0) // protocol: one byte each for width and height
    entry.writeUInt8(size & 0xff, 1) // protocol: as above
    entry.writeUInt16LE(PLANES, 4)
    entry.writeUInt16LE(BITS, 6)
    entry.writeUInt32LE(png.length, 8)
    entry.writeUInt32LE(offset, 12) // protocol: where the image starts in the file
    offset += png.length
    return entry
  })
  return Buffer.concat([head, ...entries, ...images.map((image) => image.png)])
}

/** The images of an .ico file: [{ size, png }] (for the test and for anyone checking the file). */
export function readIco(file) {
  const count = file.readUInt16LE(4)
  return Array.from({ length: count }, (_, n) => {
    const at = ICONDIR_BYTES + ICONDIRENTRY_BYTES * n
    const size = file.readUInt8(at) || 256, length = file.readUInt32LE(at + 8), offset = file.readUInt32LE(at + 12) // protocol: 0 is 256
    return { size, png: file.subarray(offset, offset + length) }
  })
}

/** Crumb's head as the app open in page draws it in the top bar: a standalone SVG (the favicon, the README's icon). */
export async function crumbHeadSvg(page) {
  await page.waitForSelector(LOGO)
  return page.evaluate(logoSvg, { selector: LOGO, paint: PAINT })
}

/** In the page: the logo as a standalone SVG, every shape painted as the page paints it, no classes, no motion. */
function logoSvg({ selector, paint }) {
  const logo = document.querySelector(selector)
  const copy = logo.cloneNode(true)
  const from = [logo, ...logo.querySelectorAll("*")], to = [copy, ...copy.querySelectorAll("*")]
  from.forEach((element, n) => {
    const style = getComputedStyle(element)
    for (const name of paint) to[n].setAttribute(name, style.getPropertyValue(name))
    to[n].removeAttribute("class")
  })
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg") // protocol: the SVG namespace
  copy.removeAttribute("aria-hidden")
  return copy.outerHTML
}

/** The .ico this script writes, drawn in browser (scripts/shots.mjs launch()) from the built app served at origin. */
export async function drawFavicon(browser, origin) {
  const context = await browser.newContext({ colorScheme: "light", reducedMotion: "reduce", deviceScaleFactor: 1 })
  try {
    const page = await context.newPage()
    await page.goto(`${origin}index.html#/`)
    const svg = await crumbHeadSvg(page)
    const images = []
    for (const size of SIZES) {
      await page.setViewportSize({ width: size, height: size })
      await page.setContent(`<!doctype html><body style="margin:0">${svg.replace("<svg", `<svg width="${size}" height="${size}"`)}</body>`)
      images.push({ size, png: await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } }) })
    }
    return ico(images)
  } finally {
    await context.close()
  }
}

/** What is out of date in the committed favicon, given the .ico the pages draw now: [] when it is the same file. */
export function staleFavicon(drawn, file = FAVICON) {
  const name = path.relative(path.join(here, ".."), file)
  if (!existsSync(file)) return [`${name} is missing`]
  return readFileSync(file).equals(drawn) ? [] : [`${name} is not what scripts/favicon.mjs draws from these pages`]
}

async function draw() {
  const { launch, serve } = await import("./shots.mjs")
  const server = await serve(), browser = await launch()
  try {
    writeFileSync(FAVICON, await drawFavicon(browser, `http://127.0.0.1:${server.address().port}/`)) // protocol: the screenshot server's loopback address
    console.log(`${path.relative(process.cwd(), FAVICON)}: Crumb's head at ${SIZES.join(", ")} px`)
  } finally {
    await browser.close()
    server.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await draw()
