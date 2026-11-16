// cake UI lint: keeps every page on shadcn components + Frosting tokens (DESIGN.md §12).
// Usage: npm run check:ui   (exit 1 on any problem)
//
// Rules
//  pages (src/pages):            no raw <button>/<input>/<select>/<textarea>/<table>/<dialog>; no style=; no arbitrary
//                                Tailwind values ([...]); no hex/rgb/hsl/oklch; no Tailwind palette colours.
//  cake components (src/components/cake): no raw form/table elements; no colour literals or palette colours;
//                                style= only for data-driven width/left in %.
//  shadcn components (src/components/ui): no colour literals (except recharts' own default strokes in selectors) and no
//                                palette colours: every colour is a token.
//  tokens: DESIGN.md §3 table == src/styles/tokens.css (light and dark), and every token used exists.
//  avatars (DESIGN.md §15): every --avatar-N stays apart from the verdict colours (solid and soft), light and dark:
//                                OKLab ΔE×100 >= 15 for normal vision and >= 8 under protan/deutan (Machado 2009),
//                                the dataviz skill's thresholds.
//  wording (DESIGN.md §2): no "person" / "people" and no "PostHog" in interface text (pages, cake components,
//                                lib); the API samples (src/data/fixtures) are interface text too, and also never
//                                say "user" for a visitor ("user agent" is fine).
//  Crumb (DESIGN.md §7): its outline and limbs (--cake-line) reach 3:1 on the page and the face (--cake-outline) 3:1 on
//                                the white body, light and dark; the white body and frosting stand out (colour or outline).
//  hover text (DESIGN.md §6, §11; scripts/hover-text.mjs): no title= hover box (a heading component's title prop
//                                excepted) and no SVG <title> in pages and components; TooltipContent and
//                                ChartTooltipContent take no className outside src/components/ui.
import { readFileSync, readdirSync, statSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { hoverTextProblems } from "./hover-text.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const repo = path.join(web, "..")
const errors = []
const rel = (f) => path.relative(web, f)
const walk = (d) => readdirSync(d).flatMap((n) => { const p = path.join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })
const lineOf = (s, i) => s.slice(0, i).split("\n").length
const err = (f, s, i, msg) => errors.push(`${rel(f)}:${lineOf(s, i)}  ${msg}`)

const PALETTE = /\b(?:bg|text|border|ring|fill|stroke|outline|decoration|from|to|via|divide|shadow|caret|accent|placeholder)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|black|white)(?:-\d+)?(?:\/\d+)?\b/g
const COLOR_LIT = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(/g
const RAW_EL = /<(button|input|select|textarea|table|dialog)\b/g
const ARBITRARY = /(?:^|[\s"'`])(?:[a-z0-9:-]+:)*-?[a-z][a-z0-9-]*-\[[^\]\s]+\]/g

function scan(f, { raw = false, style = "none", arbitrary = false, colorSelectorsOk = false }, s = readFileSync(f, "utf8")) {
  for (const m of s.matchAll(PALETTE)) err(f, s, m.index, `Tailwind palette colour "${m[0]}": use a token class (bg-primary, text-agent-foreground …)`)
  for (const m of s.matchAll(COLOR_LIT)) {
    if (colorSelectorsOk && /\[(?:stroke|fill)='#[0-9a-fA-F]+'\]/.test(s.slice(m.index - 10, m.index + 12))) continue
    err(f, s, m.index, `colour literal "${m[0]}": colours live only in src/styles/tokens.css`)
  }
  if (raw) for (const m of s.matchAll(RAW_EL)) err(f, s, m.index, `raw <${m[1]}>: use the shadcn component (Button, Input, Select, Table, Dialog …)`)
  if (style === "none") for (const m of s.matchAll(/\bstyle=/g)) err(f, s, m.index, "style= in a page: add a component or a variant instead")
  if (style === "data") for (const m of s.matchAll(/style=\{\{([^}]*)\}\}/g)) {
    const keys = [...m[1].matchAll(/([a-zA-Z"'-]+)\s*:/g)].map((k) => k[1].replace(/["']/g, ""))
    if (keys.some((k) => !["width", "left"].includes(k))) err(f, s, m.index, `style= with ${keys.join(", ")}: only data-driven width/left are allowed`)
  }
  if (arbitrary) for (const m of s.matchAll(ARBITRARY)) err(f, s, m.index, `arbitrary Tailwind value "${m[0].trim()}" in a page: use the scale, a component or a variant`)
}

for (const f of walk(path.join(web, "src/pages"))) scan(f, { raw: true, style: "none", arbitrary: true })
for (const f of walk(path.join(web, "src/components/cake"))) scan(f, { raw: true, style: "data" })
for (const f of walk(path.join(web, "src/components/ui"))) scan(f, { style: "ignore", colorSelectorsOk: true })
scan(path.join(web, "src/index.css"), { style: "ignore" })

// hover text: one tooltip, never the browser's own title box
for (const f of ["src/pages", "src/components/cake", "src/components/ui"].flatMap((d) => walk(path.join(web, d))).filter((f) => f.endsWith(".tsx"))) {
  const s = readFileSync(f, "utf8")
  for (const { index, message } of hoverTextProblems(f, s)) err(f, s, index, message)
}

// tokens.css <-> DESIGN.md
const tokensCss = readFileSync(path.join(web, "src/styles/tokens.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "")
const block = (re) => Object.fromEntries([...(tokensCss.match(re)?.[1] ?? "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))
const light = block(/:root\s*\{([\s\S]*?)\n\}/), dark = block(/\.dark\s*\{([\s\S]*?)\n\}/)
const doc = readFileSync(path.join(repo, "DESIGN.md"), "utf8")
const table = Object.fromEntries([...doc.matchAll(/^\|\s*`(--[\w-]+)`\s*\|\s*`([^`]*)`\s*\|\s*([^|]+?)\s*\|/gm)].map((m) => [m[1], [m[2].trim(), m[3].trim().replace(/`/g, "")]]))
for (const [k, v] of Object.entries(light)) {
  if (!table[k]) { errors.push(`DESIGN.md: token ${k} missing from the §3 table`); continue }
  if (table[k][0] !== v) errors.push(`DESIGN.md: ${k} light ${table[k][0]} != tokens.css ${v}`)
  const d = dark[k] ?? "same as light"
  if (table[k][1] !== d) errors.push(`DESIGN.md: ${k} dark ${table[k][1]} != tokens.css ${d}`)
}
for (const k of Object.keys(table)) if (!(k in light)) errors.push(`DESIGN.md: ${k} is in the table but not in tokens.css`)
for (const k of Object.keys(dark)) if (!(k in light)) errors.push(`tokens.css: ${k} only in .dark`)

// avatar colours vs the verdict colours
const hexRgb = (v) => { const h = /^#([0-9a-f]{6})$/i.exec(v ?? ""); return h ? [0, 2, 4].map((i) => parseInt(h[1].slice(i, i + 2), 16)) : null }
const MACHADO = { protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]] }
const linRgb = (c) => c.map((x) => { x /= 255; return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4 })
const oklab = ([r, g, b]) => {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), q = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * q, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * q, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * q]
}
const sim = (c, k) => { const v = linRgb(c); return k ? MACHADO[k].map((row) => Math.min(1, Math.max(0, row[0] * v[0] + row[1] * v[1] + row[2] * v[2]))) : v }
const dE = (a, b, k) => { const p = oklab(sim(a, k)), q = oklab(sim(b, k)); return 100 * Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) }
const avatarTokens = Object.keys(light).filter((k) => /^--avatar-\d+$/.test(k))
const avatarReport = []
for (const mode of ["light", "dark"]) {
  const t = { ...light, ...(mode === "dark" ? dark : {}) }
  let wn = 99, wc = 99
  for (const a of avatarTokens) for (const v of ["--human", "--agent", "--unsure", "--human-soft", "--agent-soft", "--unsure-soft"]) {
    const A = hexRgb(t[a]), V = hexRgb(t[v])
    if (!A || !V) { errors.push(`avatar ${mode}: ${a} or ${v} is not a #rrggbb colour`); continue }
    const n = dE(A, V), c = Math.min(dE(A, V, "protan"), dE(A, V, "deutan"))
    wn = Math.min(wn, n); wc = Math.min(wc, c)
    if (n < 15 || c < 8) errors.push(`avatar ${mode}: ${a} ${t[a]} too close to ${v} ${t[v]} (ΔE ${n.toFixed(1)} normal, ${c.toFixed(1)} colour-blind; needs 15 / 8)`)
  }
  avatarReport.push(`${mode} ΔE ≥ ${wn.toFixed(1)}, colour-blind ≥ ${wc.toFixed(1)}`)
}

// Crumb's silhouette (DESIGN.md §7): the white body and the frosting must stand out from the page, light and dark:
// the colour itself or the outline reaches 3:1 against --background.
const lum = (c) => { const [r, g, b] = linRgb(c); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
const crumbReport = []
for (const mode of ["light", "dark"]) {
  const t = { ...light, ...(mode === "dark" ? dark : {}) }
  const bg = hexRgb(t["--background"]), line = ratio(hexRgb(t["--cake-line"]), bg), face = ratio(hexRgb(t["--cake-outline"]), hexRgb(t["--cake-shine"]))
  if (line < 3) errors.push(`crumb ${mode}: its outline and limbs (--cake-line ${t["--cake-line"]}) are ${line.toFixed(2)}:1 on the page ${t["--background"]} (needs 3)`)
  if (face < 3) errors.push(`crumb ${mode}: the face (--cake-outline) is ${face.toFixed(2)}:1 on the white body (needs 3)`)
  for (const k of ["--cake-shine", "--cake-frosting"]) {
    const fill = ratio(hexRgb(t[k]), bg)
    if (Math.max(fill, line) < 3) errors.push(`crumb ${mode}: neither ${k} ${t[k]} (${fill.toFixed(2)}:1) nor the outline (${line.toFixed(2)}:1) reaches 3:1 on ${t["--background"]}`)
  }
  crumbReport.push(`${mode} outline + limbs ${line.toFixed(2)}, face on body ${face.toFixed(2)}, body ${ratio(hexRgb(t["--cake-shine"]), bg).toFixed(2)}, frosting ${ratio(hexRgb(t["--cake-frosting"]), bg).toFixed(2)}`)
}

// wording (DESIGN.md §2): interface text names visitors Human / Agent, never person or people, and never names PostHog
// (comments are skipped). Code can't be checked for "user" (the User icon), but the API samples can: every string there.
const WHO = /\b(person|people|persons)\b|\bPostHog\b/i
const WHO_IN_DATA = /\b(person|people|persons)\b|\busers?\b(?![ -]agent)|\bPostHog\b/i
for (const f of [...walk(path.join(web, "src/pages")), ...walk(path.join(web, "src/components/cake")), ...walk(path.join(web, "src/lib"))]) {
  if (!/\.(tsx?|html|js)$/.test(f)) continue
  readFileSync(f, "utf8").split("\n").forEach((line, i) => {
    const t = line.trim()
    if (/^(\/\/|\/\*|\*|\{\/\*)/.test(t)) return
    const code = line.replace(/(^|[^:])\/\/.*$/, "$1")
    const m = code.match(WHO)
    if (m) errors.push(`${rel(f)}:${i + 1}  "${m[0]}" in interface text: call visitors Human / Agent, never name PostHog (DESIGN.md §2)`)
  })
}
for (const f of walk(path.join(web, "src/data/fixtures"))) {
  const strings = []
  const visit = (v) => { if (typeof v === "string") strings.push(v); else if (v && typeof v === "object") Object.values(v).forEach(visit) }
  visit(JSON.parse(readFileSync(f, "utf8")))
  for (const text of strings) {
    const m = text.match(WHO_IN_DATA)
    if (m) errors.push(`${rel(f)}  "${m[0]}" in "${text.slice(0, 60)}": call visitors Human / Agent, never name PostHog (DESIGN.md §2)`)
  }
}

// every var(--x) used in our CSS exists: tokens + Tailwind theme names
const tokenNames = new Set(Object.keys(light))
const known = new Set([...tokenNames, ...[...readFileSync(path.join(web, "src/index.css"), "utf8").matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1])])
for (const [f, names] of [[path.join(web, "src/index.css"), known]]) {
  const s = readFileSync(f, "utf8")
  for (const m of s.matchAll(/var\((--[\w-]+)/g)) if (!names.has(m[1]) && !m[1].startsWith("--tw-")) err(f, s, m.index, `unknown token ${m[1]}`)
}

if (errors.length) { console.log(`check:ui FAIL (${errors.length})`); for (const e of errors) console.log("  " + e); process.exit(1) }
console.log(`check:ui OK · ${Object.keys(light).length} tokens (${Object.keys(dark).length} with dark values) match DESIGN.md · pages use components and tokens only · hover text only in the theme tooltip`)
console.log(`  ${avatarTokens.length} avatar colours vs the verdict colours: ${avatarReport.join(" · ")}`)
console.log(`  Crumb (outline and limbs on the page, face on the white body: each >= 3:1): ${crumbReport.join(" · ")}`)
