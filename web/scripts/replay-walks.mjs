// The walks the sample replays are recorded from: what each sample session in src/data/fixtures/ does in the
// test site's shop (tests/site, the demo shop until 0.4.0), and when. scripts/replay-fixtures.mjs runs them in Chromium against a scratch Agent Cake and keeps the
// rrweb events its cake.js recorded. Times are milliseconds from the moment the first page is asked for (the
// session's ms 0); each walk ends, and its tab closes, at its sample's duration.
//
// A human moves the mouse along curves at an uneven pace, scrolls in uneven steps and clicks near (not at) the middle
// of things; an agent clicks the exact middle with no mouse travel and fills fields in one go. Inputs are masked by
// cake.js, so what is typed never reaches a recording; the details are made up anyway (the shop asks for that).
const FRAME_MS = 16 // one mouse move per display frame, like a real pointer
const EDGE_PX = 80 // a human scrolls something into view, this far from the window's edge, before clicking it
const MADE_UP = { email: "walker@example.com", fullname: "Demo Walker", address: "1 Example Street", city: "Sampleton", postcode: "00000", cardname: "Demo Walker" }
export const TYPED = Object.values(MADE_UP)
export const VIEWPORT = { width: 1280, height: 800 }

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** A small seeded random generator (mulberry32), so every run takes the same curves. */
function seeded(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const between = (rng, low, high) => low + rng() * (high - low)
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)
const bezier = (p0, p1, p2, p3, t) => {
  const u = 1 - t
  const mix = (k) => u * u * u * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t * t * t * p3[k]
  return { x: mix("x"), y: mix("y") }
}

/** What a walk can do on its page, timed from t0 (epoch ms of its ms 0). actions: what it did, for the sample's
 *  "Every action" list (never what was typed). */
export function walker(page, t0, seed) {
  const rng = seeded(seed)
  let mouse = { x: 0, y: 0 } // where Playwright's pointer starts
  const actions = []
  const at = async (ms) => { const wait = t0 + ms - Date.now(); if (wait > 0) await sleep(wait) }
  const here = () => { const u = new URL(page.url()); return u.pathname + u.search }
  const log = (who, what) => actions.push({ at_ms: Math.max(0, Date.now() - t0), who, what, page: here() })
  const box = async (selector) => {
    const b = await page.locator(selector).first().boundingBox()
    if (!b) throw new Error(`${selector} is not on the page`)
    return b
  }

  /** A human pointer: a curve from where it is to `to`, over about `ms`. */
  async function curve(to, ms) {
    const from = { ...mouse }
    const dx = to.x - from.x, dy = to.y - from.y, length = Math.hypot(dx, dy) || 1
    const normal = { x: -dy / length, y: dx / length }
    const bend = [between(rng, -0.3, 0.3) * length, between(rng, -0.3, 0.3) * length]
    const c1 = { x: from.x + dx * 0.3 + normal.x * bend[0], y: from.y + dy * 0.3 + normal.y * bend[0] }
    const c2 = { x: from.x + dx * 0.7 + normal.x * bend[1], y: from.y + dy * 0.7 + normal.y * bend[1] }
    const steps = Math.max(6, Math.round(ms / FRAME_MS)), start = Date.now()
    for (let i = 1; i <= steps; i++) {
      const p = bezier(from, c1, c2, to, easeInOut(i / steps))
      await page.mouse.move(p.x + between(rng, -1, 1), p.y + between(rng, -1, 1))
      const wait = start + (ms * i * between(rng, 0.85, 1.15)) / steps - Date.now()
      if (wait > 0) await sleep(wait)
    }
    mouse = { ...to }
  }

  const human = {
    /** Wander to a point of the page (as a share of the window), slowly. */
    wander: (fx, fy, ms) => curve({ x: VIEWPORT.width * fx, y: VIEWPORT.height * fy }, ms),
    /** Move to something and click it somewhere near its middle. */
    async click(selector, what, ms = between(rng, 700, 1200)) {
      let b = await box(selector)
      const off = b.y < EDGE_PX ? b.y - EDGE_PX : b.y + b.height > VIEWPORT.height - EDGE_PX ? b.y + b.height - VIEWPORT.height + EDGE_PX : 0
      if (off) { await human.scroll(off); b = await box(selector) }
      await curve({ x: b.x + b.width * between(rng, 0.3, 0.7), y: b.y + b.height * between(rng, 0.3, 0.7) }, ms)
      await sleep(between(rng, 80, 220))
      log("human", what)
      await page.mouse.down(); await sleep(between(rng, 60, 130)); await page.mouse.up()
    },
    /** Scroll by about `pixels` (negative: up) in uneven wheel steps. */
    async scroll(pixels, what) {
      if (what) log("human", what)
      let left = pixels
      while (Math.abs(left) > 1) {
        const step = Math.sign(left) * Math.min(Math.abs(left), between(rng, 40, 140))
        await page.mouse.wheel(0, step); left -= step
        await sleep(between(rng, 40, 260))
      }
    },
  }

  const agent = {
    /** Click the exact middle, with no pointer travel before it. */
    async click(selector, what) {
      const target = page.locator(selector).first()
      await target.scrollIntoViewIfNeeded() // a jump, never a wheel
      const b = await box(selector)
      log("agent", what)
      mouse = { x: b.x + b.width / 2, y: b.y + b.height / 2 }
      await target.click() // Playwright clicks the middle, the pointer jumping straight there
    },
    async fill(selector, value, what) { log("agent", what); await page.locator(selector).fill(value) },
    async select(selector, value, what) { log("agent", what); await page.locator(selector).selectOption(value) },
  }

  /** Neither kind of pointer: one straight, steady move (the stretch the model is not sure about). */
  async function straight(fx, fy, ms) {
    const steps = Math.round(ms / FRAME_MS), from = { ...mouse }, to = { x: VIEWPORT.width * fx, y: VIEWPORT.height * fy }
    for (let i = 1; i <= steps; i++) { await page.mouse.move(from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps); await sleep(FRAME_MS) }
    mouse = to
  }

  return { at, log, human, agent, straight, actions, page }
}

const PRODUCT = 'a:text-is("Classic T-shirt")'
const CHECKOUT_LABELS = { email: "Email", fullname: "Full name", address: "Street address", city: "City", postcode: "Postcode" }
const ON_PRODUCT = "**/demo/product?id=classic-tee"

/** Each sample session that has a replay: its id, how long it lasts, and what it does. */
export const WALKS = [
  {
    id: "19fc-90", duration_ms: 13000, seed: 19, // Automated browser: a script, quick and straight
    async run({ at, page, agent, log }, base) {
      await page.goto(`${base}/demo`)
      await at(2500); await agent.fill("#q", "t-shirt", "Type in “Search products” (0 ms between keys)")
      await at(3500); log("agent", "Press Enter"); await Promise.all([page.waitForURL("**/demo?q=*"), page.press("#q", "Enter")])
      await at(6500); await Promise.all([page.waitForURL(ON_PRODUCT), agent.click(PRODUCT, "Click “Classic T-shirt” (centre hit)")])
      await at(10500); await agent.click("input[name=color][value=Blue]", "Click “Blue” (centre hit)")
    },
  },
  {
    id: "6e0f-13", duration_ms: 48000, seed: 613, // an AI agent in a real browser: thinks between steps, then acts at once
    async run({ at, page, agent }, base) {
      await page.goto(`${base}/demo?q=t-shirt`) // the shop's search for t-shirts, opened straight away
      await at(5000); await Promise.all([page.waitForURL(ON_PRODUCT), agent.click(PRODUCT, "Click “Classic T-shirt” (centre hit)")])
      await at(12000); await agent.click("input[name=color][value=Blue]", "Click “Blue” (centre hit)")
      await at(18000); await agent.select("#size", "M", "Select size M")
      await at(24000); await agent.click("#add", "Click “Add to cart” (centre hit)")
      await at(30000); await Promise.all([page.waitForURL("**/demo/cart"), agent.click('#msg a:text-is("Go to cart")', "Click “Go to cart” (centre hit)")])
      await at(37000); await Promise.all([page.waitForURL("**/demo/checkout"), agent.click("#checkout", "Click “Checkout” (centre hit)")])
      await at(43000); await agent.fill("#email", MADE_UP.email, "Type in “Email” (0 ms between keys)")
    },
  },
  {
    id: "7f3a-c1", duration_ms: 96400, seed: 731, // a human, then an agent from 0:38.56, not sure 1:20–1:23, the human again
    async run({ at, page, human, agent, straight }, base) {
      await page.goto(`${base}/demo?cat=Tops`) // arrives on the shop's Tops (from a link)
      await at(1200); await human.wander(0.62, 0.42, 1300); await human.wander(0.35, 0.58, 1100)
      await at(4000); await human.scroll(520, "Scroll")
      await at(6500); await human.wander(0.7, 0.5, 1400); await human.wander(0.45, 0.35, 900)
      await at(9000); await human.scroll(260)
      await at(12000); await human.scroll(-780, "Scroll back up")
      await at(15000); await human.wander(0.2, 0.62, 1600); await human.wander(0.3, 0.52, 1800)
      await at(19800); await Promise.all([page.waitForURL(ON_PRODUCT), human.click(PRODUCT, "Click “Classic T-shirt”", 1100)])
      await at(23500); await human.wander(0.55, 0.5, 1200)
      await at(25000); await human.scroll(640, "Scroll to the reviews")
      await at(28500); await human.wander(0.4, 0.62, 1500); await human.wander(0.66, 0.4, 1300)
      await at(33000); await human.scroll(-700, "Scroll back up")
      await at(35500); await human.wander(0.74, 0.3, 1200)
      await at(38560); await agent.click("input[name=color][value=Blue]", "Click “Blue” (centre hit)")
      await at(41000); await agent.select("#size", "M", "Select size M")
      await at(52000); await agent.fill("#qty", "1", "Type in “Quantity” (0 ms between keys)")
      await at(64000); await agent.click("#add", "Click “Add to cart” (centre hit)")
      await at(66000); await Promise.all([page.waitForURL("**/demo/cart"), agent.click('#msg a:text-is("Go to cart")', "Click “Go to cart” (centre hit)")])
      await at(70000); await Promise.all([page.waitForURL("**/demo/checkout"), agent.click("#checkout", "Click “Checkout” (centre hit)")])
      for (const [i, [field, label]] of Object.entries(CHECKOUT_LABELS).entries()) {
        await at(73000 + i * 1000); await agent.fill(`#${field}`, MADE_UP[field], `Fill “${label}” (0 ms between keys)`)
      }
      await at(78000); await agent.select("#country", "Other", "Select country")
      await at(79000); await agent.fill("#cardname", MADE_UP.cardname, "Fill “Name on card” (0 ms between keys)")
      await at(81000); await straight(0.5, 0.45, 900)
      await at(84500); await human.wander(0.6, 0.55, 1300)
      await at(87000); await human.scroll(-600, "Scroll back up")
      await at(89500); await human.scroll(900)
      await at(91500); await human.click("#agree", "Tick “Confirm that this is a demo”", 1300)
      await at(94000); await human.wander(0.55, 0.7, 1500)
    },
  },
]
