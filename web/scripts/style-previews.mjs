// The Style menu's previews (src/assets/styles/<style>.png, components/cake/style-menu.tsx): the dashboard's first
// screen in each style, 1280 x 800, shrunk to 480 x 300 by the browser's own high-quality scaling. The dashboard is
// cake's own answers on the fixed test library at a fixed moment (fixtures/library/, LIBRARY), taken the way the visual
// baseline is (scripts/visual.mjs), so no visitor, address or folder of any computer can be in it. PNG: the only kind
// of picture AgentCake serves (agentcake/data/web.json). The previews are part of the build, so build again after.
//   cd web && npm run build && node scripts/style-previews.mjs && npm run build
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { PNG } from "pngjs"
import { LIBRARY } from "./fixture-api.mjs"
import { STYLES, launch, pickStyle, serve, shoot } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(here, "..", "src", "assets", "styles")
const VIEW = { width: 1280, height: 800 }
const PREVIEW = { width: 480, height: 300 }
const RGB = 2 // pngjs colour type: no alpha channel
const MOST_DEFLATE = 9 // zlib's highest level

/** A screenshot scaled to PREVIEW by the browser's own high-quality scaling, as an RGB PNG. */
async function shrink(page, png) {
  const scaled = await page.evaluate(async ({ data, width, height }) => {
    const image = new Image()
    image.src = `data:image/png;base64,${data}`
    await image.decode()
    const canvas = Object.assign(document.createElement("canvas"), { width, height })
    const draw = canvas.getContext("2d")
    draw.imageSmoothingQuality = "high"
    draw.drawImage(image, 0, 0, width, height)
    return canvas.toDataURL("image/png").split(",")[1]
  }, { data: png.toString("base64"), ...PREVIEW })
  const pixels = PNG.sync.read(Buffer.from(scaled, "base64"))
  return PNG.sync.write(pixels, { colorType: RGB, inputHasAlpha: true, deflateLevel: MOST_DEFLATE })
}

const lib = await serve(undefined, { fixtures: LIBRARY })
const origin = `http://127.0.0.1:${lib.address().port}/`
const browser = await launch()
try {
  for (const style of STYLES) {
    const context = await browser.newContext({ viewport: VIEW, colorScheme: "light", reducedMotion: "reduce", deviceScaleFactor: 1 })
    await pickStyle(context, style)
    const page = await context.newPage()
    await shoot(page, `${origin}index.html#/dashboard`)
    const png = await shrink(page, await page.screenshot({ animations: "disabled", caret: "hide" }))
    const file = path.join(OUT, `${style}.png`)
    await writeFile(file, png)
    console.log(`${style}: ${path.relative(process.cwd(), file)}, ${png.length} bytes`)
    await context.close()
  }
} finally {
  await browser.close()
  lib.close()
}
