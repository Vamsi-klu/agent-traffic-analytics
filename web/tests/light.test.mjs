// The pages are light only (DESIGN.md §9), in both styles (§17): in Chromium, against the built app, every element of
// the component overview (every component and variant) is painted the same under a dark system as under a light one,
// the root never gets a .dark class, and ?theme=dark in the address changes nothing. Usage: node --test tests/
import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { startApp } from "./app.mjs"
import { STYLES, pickStyle, shoot } from "../scripts/shots.mjs"

/** What makes up an element's look: its colours, its frame and shadow, its fill and line, and the scheme it asks of
 *  the browser's own controls. */
const PAINT = ["color", "background-color", "background-image", "border-top-color", "border-right-color", "border-bottom-color",
  "border-left-color", "outline-color", "box-shadow", "fill", "stroke", "opacity", "color-scheme"]
const ROUTE = "#/components"
let app
before(async () => { app = await startApp() })
after(() => app?.close())

/** The component overview opened in `style` under a system in `scheme`, `query` added to the address: the style the
 *  root shows, whether it has .dark, and every element's PAINT values, in document order. */
async function paint(style, scheme, query = "") {
  const context = await app.browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: scheme, reducedMotion: "reduce" })
  await pickStyle(context, style)
  try {
    const page = await context.newPage()
    await shoot(page, `${app.origin}/index.html${query}${ROUTE}`)
    return await page.evaluate((props) => ({
      style: document.documentElement.dataset.style ?? "cake",
      dark: document.documentElement.classList.contains("dark"),
      looks: [...document.querySelectorAll("*")].map((el) => {
        const style = getComputedStyle(el)
        return `${el.tagName.toLowerCase()}.${el.getAttribute("class") ?? ""} ${props.map((p) => `${p}: ${style.getPropertyValue(p)}`).join("; ")}`
      }),
    }), PAINT)
  } finally {
    await context.close()
  }
}

/** The elements painted differently from `light`, at most a few, for the failure message. */
function differences(light, other) {
  assert.equal(other.looks.length, light.looks.length, "the same elements on both pages")
  return light.looks.flatMap((look, i) => (look === other.looks[i] ? [] : [`${look}\n  became ${other.looks[i]}`])).slice(0, 3)
}

for (const style of STYLES) {
  test(`${style}: under a dark system the pages stay light: no .dark on the root, every element painted as under a light system`, async () => {
    const light = await paint(style, "light"), dark = await paint(style, "dark")
    assert.deepEqual([light.style, dark.style], [style, style])
    assert.equal(light.dark, false)
    assert.equal(dark.dark, false, "the root has .dark under a dark system")
    assert.deepEqual(differences(light, dark), [])
  })

  test(`${style}: ?theme=dark in the address changes nothing: the pages stay light`, async () => {
    const light = await paint(style, "light"), forced = await paint(style, "light", "?theme=dark")
    assert.equal(forced.dark, false, "the root has .dark with ?theme=dark")
    assert.deepEqual(differences(light, forced), [])
  })
}
