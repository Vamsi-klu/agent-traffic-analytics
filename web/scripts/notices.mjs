// The third-party notices of the local pages (release 0.4.0, job web-notices): a Vite plugin that adds one plain-text
// file to dist/ (notices.json "file", THIRD_PARTY_NOTICES.txt) when `npm run build` writes it. The release copies dist/
// into the package (tools/releasing/webapp.py), so every wheel carries the copyright and licence notices of what its
// compiled pages bundle, as MIT, ISC, BSD and Apache-2.0 ask.
//
// What is listed is read from the bundle, never from package.json: every npm package with code in a chunk, every
// package whose styles the stylesheets @import (Tailwind compiles those itself, so they never become modules of the
// bundle: tailwindcss, tw-animate-css, shadcn's tailwind.css), and the files of notices.json "files" that are in dist/.
// For each package: its version, the licence its package.json declares, and its licence and notice files, unchanged
// (notices.json "licence_files"); a package that ships none must have its text in notices.json "texts", or the build
// stops. The file depends only on the installed packages, so the same package-lock.json gives the same bytes.
//
// Modelled on Vite's own build.license option (vite 8.3.5, src/node/plugins/license.ts, MIT): packages found from the
// chunks' modules by their nearest package.json, their licence file read from the package's folder. Written anew
// because that option leaves out what these pages need: the packages of the stylesheets, NOTICE files (es-toolkit's
// notice for its Lodash-derived code), the texts of packages that ship no licence file, and the fonts.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import path from "node:path"

const IN_NODE_MODULES = /[\\/]node_modules[\\/]/
const NODE_MODULES = "node_modules"
const MANIFEST = "package.json"
// The style languages Vite compiles into the stylesheet (its CSS_LANGS_RE).
const STYLE_FILE = /\.(css|less|sass|scss|styl|stylus|pcss|postcss|sss)$/
const STYLE_IMPORT = /@import\s+(?:url\(\s*)?["']([^"']+)["']/g
// A stylesheet from another site is loaded by the browser, not bundled: http:, https:, data:, //host/...
const NOT_BUNDLED = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i
const RULE_WIDTH = 80 // as wide as the lines of the licence texts
export const ENTRY_RULE = "=".repeat(RULE_WIDTH)

export const readJson = (file) => JSON.parse(readFileSync(file, "utf8"))

/** A text file as the notices copy it: UTF-8 without a byte order mark, \n line ends, no trailing blank lines. */
export function readText(file) {
  return readFileSync(file, "utf8").replace(/^﻿/, "").replace(/\r\n?/g, "\n").trimEnd()
}

/** The licence a package.json declares: an SPDX expression, or the older {type} and [{type}] forms; "" if none. */
export function declaredLicence(manifest) {
  const { license, licenses } = manifest
  if (typeof license === "string") return license.trim()
  if (license && typeof license.type === "string") return license.type.trim()
  if (Array.isArray(licenses)) return licenses.map((entry) => entry?.type ?? entry).filter(Boolean).join(" OR ")
  return ""
}

/** The package a file in node_modules belongs to: the nearest package.json with a name (a dist/package.json that
 *  only says "type": "module" belongs to the package above it). null when there is none inside node_modules. */
export function packageOf(file, cache = new Map()) {
  for (let dir = path.dirname(file); path.basename(dir) !== NODE_MODULES; dir = path.dirname(dir)) {
    if (path.dirname(dir) === dir) return null
    if (!cache.has(dir)) {
      const manifestFile = path.join(dir, MANIFEST)
      const manifest = existsSync(manifestFile) ? readJson(manifestFile) : null
      cache.set(dir, manifest?.name ? { name: manifest.name, version: manifest.version ?? "", manifest, dir } : null)
    }
    if (cache.get(dir)) return cache.get(dir)
  }
  return null
}

/** A package's licence and notice files: the top-level files whose name starts like one of prefixes, sorted. */
export function licenceFiles(dir, prefixes) {
  return readdirSync(dir)
    .filter((name) => prefixes.some((prefix) => name.toLowerCase().startsWith(prefix)))
    .filter((name) => statSync(path.join(dir, name)).isFile())
    .sort()
}

/** The folder of package name as Node finds it from fromDir: node_modules/<name> here or in a folder above. */
function packageDir(name, fromDir) {
  for (let dir = fromDir; ; dir = path.dirname(dir)) {
    const candidate = path.join(dir, NODE_MODULES, name)
    if (existsSync(path.join(candidate, MANIFEST))) return candidate
    if (path.dirname(dir) === dir) return null
  }
}

/** The stylesheet a bare @import names, the way Tailwind resolves it (the "style" condition of the package's
 *  exports, else its "style" field, else the file itself); null when none can be found. */
function styleEntry(pkg, subpath) {
  const { exports: map, style } = pkg.manifest
  const target = map && typeof map === "object" ? map[subpath ? `./${subpath}` : "."] : undefined
  const chosen = typeof target === "string" ? target : target?.style ?? target?.default
  const file = chosen ?? (subpath || style)
  return file && STYLE_FILE.test(file) ? path.join(pkg.dir, file) : null
}

/** Every package the stylesheets reach through @import, from files (stylesheets in the bundle), following the
 *  imports of the project's own stylesheets and of the packages' ones. */
export function stylePackages(files, cache = new Map()) {
  const found = new Map(), seen = new Set()
  const visit = (file) => {
    if (seen.has(file) || !existsSync(file)) return
    seen.add(file)
    for (const [, specifier] of readFileSync(file, "utf8").matchAll(STYLE_IMPORT)) {
      if (NOT_BUNDLED.test(specifier)) continue
      if (specifier.startsWith(".")) { visit(path.resolve(path.dirname(file), specifier)); continue }
      const parts = specifier.split("/"), nameParts = specifier.startsWith("@") ? 2 : 1
      const dir = packageDir(parts.slice(0, nameParts).join("/"), path.dirname(file))
      const pkg = dir && packageOf(path.join(dir, MANIFEST), cache)
      if (!pkg) continue
      found.set(`${pkg.name}@${pkg.version}`, pkg)
      const entry = styleEntry(pkg, parts.slice(nameParts).join("/"))
      if (entry) visit(entry)
    }
  }
  files.forEach(visit)
  return [...found.values()]
}

/** The packages with code or styles in the bundle (Rollup's or Rolldown's output bundle), each once. */
export function bundledPackages(bundle, cache = new Map()) {
  const found = new Map(), stylesheets = []
  for (const chunk of Object.values(bundle)) {
    if (chunk.type !== "chunk") continue
    for (const [id, module] of Object.entries(chunk.modules)) {
      if (id.startsWith("\0")) continue // a bundler's virtual module, not a file
      const file = id.split("?")[0]
      const isStyle = STYLE_FILE.test(file)
      if (isStyle) stylesheets.push(file) // its styles went into the .css file, so its rendered length is 0
      if (!IN_NODE_MODULES.test(file) || !(isStyle || module.renderedLength > 0)) continue
      const pkg = packageOf(file, cache)
      if (pkg) found.set(`${pkg.name}@${pkg.version}`, pkg)
    }
  }
  for (const pkg of stylePackages(stylesheets, cache)) found.set(`${pkg.name}@${pkg.version}`, pkg)
  return [...found.values()]
}

/** The entries of notices.json "files" whose file the build put into dist/ (an asset's original file). */
export function bundledFiles(bundle, root, entries) {
  const originals = new Set()
  for (const output of Object.values(bundle)) {
    if (output.type !== "asset") continue
    for (const name of output.originalFileNames ?? []) originals.add(path.resolve(root, name))
  }
  return entries.filter((entry) => originals.has(path.resolve(root, entry.file)))
}

const byText = (a, b) => (a < b ? -1 : a > b ? 1 : 0) // by code unit, the same on every machine and locale

/** One package's entry, or a problem when it has no licence text (or notices.json's text for it is out of date). */
function packageEntry(pkg, settings) {
  const files = licenceFiles(pkg.dir, settings.licence_files.prefixes)
  const kept = settings.texts.packages[pkg.name]
  const title = `${pkg.name} ${pkg.version}`
  if (files.length && kept) return { problem: `${title} ships its own licence file now: remove it from notices.json "texts"` }
  if (kept && kept.version !== pkg.version) {
    return { problem: `${title}: notices.json "texts" has its licence for ${kept.version}; check this version's, update it` }
  }
  const texts = files.map((name) => ({ title: name, text: readText(path.join(pkg.dir, name)) }))
  if (kept) texts.push({ title: `LICENSE (not in the npm package; from ${kept.source})`, text: kept.text.trimEnd() })
  if (!texts.length) return { problem: `${title} ships no licence file: add its licence text to notices.json "texts"` }
  return { title, licence: declaredLicence(pkg.manifest), texts }
}

/** One entry of notices.json "files". */
function fileEntry(entry, root) {
  const licenceFile = path.resolve(root, entry.licence_file)
  if (!existsSync(licenceFile)) return { problem: `${entry.file}: its licence file ${entry.licence_file} is missing` }
  const texts = [{ title: path.basename(licenceFile), text: readText(licenceFile) }]
  return { title: path.basename(entry.file), licence: entry.license, texts }
}

/** The notices for these packages and files: {text, entries, problems}; text is only meant to be written when there
 *  is no problem. */
export function buildNotices(packages, files, settings, root) {
  const sorted = [...packages].sort((a, b) => byText(a.name, b.name) || byText(a.version, b.version))
  const results = [...sorted.map((pkg) => packageEntry(pkg, settings)), ...files.map((entry) => fileEntry(entry, root))]
  const bundledNames = new Set(packages.map((pkg) => pkg.name))
  const unused = Object.keys(settings.texts.packages).filter((name) => !bundledNames.has(name))
  const problems = [
    ...results.filter((result) => result.problem).map((result) => result.problem),
    ...unused.map((name) => `${name} is no longer bundled: remove it from notices.json "texts"`),
  ]
  const entries = results.filter((result) => !result.problem)
  return { text: formatNotices(entries, settings.header), entries, problems }
}

/** The plain-text file: the header, the list of what is in it, then each entry with its licence texts. */
export function formatNotices(entries, header) {
  const label = (entry) => `${entry.title} (${entry.licence || "no licence declared"})`
  const lines = [...header, "", ...entries.map((entry) => `  ${label(entry)}`)]
  for (const entry of entries) {
    lines.push("", ENTRY_RULE, entry.title, `License: ${entry.licence || "not declared"}`)
    for (const text of entry.texts) lines.push("", `----- ${text.title} -----`, "", text.text)
  }
  return lines.join("\n") + "\n"
}

/** The Vite plugin: settingsFile is notices.json, root the folder its paths are relative to (web/). */
export function thirdPartyNotices({ root, settingsFile }) {
  return {
    name: "cake-third-party-notices",
    apply: "build",
    enforce: "post",
    generateBundle(_, bundle) {
      const settings = readJson(settingsFile)
      const cache = new Map()
      const files = bundledFiles(bundle, root, settings.files.entries)
      const notices = buildNotices(bundledPackages(bundle, cache), files, settings, root)
      if (notices.problems.length) {
        this.error(`third-party notices (${path.basename(settingsFile)}):\n  ${notices.problems.join("\n  ")}`)
      }
      this.emitFile({ type: "asset", fileName: settings.file, source: notices.text })
    },
  }
}
