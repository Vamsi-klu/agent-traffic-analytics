// Tests for the third-party notices of the local pages (scripts/notices.mjs, job web-notices): which packages count as
// bundled (code in a chunk, or styles a stylesheet imports), which of their files are copied, what stops the build,
// and that the real build lists every package it bundles, each with its licence text, and nothing else.
// Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { after, test } from "node:test"
import { fileURLToPath } from "node:url"
import { build } from "vite"
import {
  ENTRY_RULE, buildNotices, bundledFiles, bundledPackages, declaredLicence, licenceFiles, packageOf, readJson, readText,
} from "./notices.mjs"

const web = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")
const SETTINGS = readJson(path.join(web, "notices.json"))
const MIT = "MIT License\n\nCopyright (c) 2026 A Maintainer\n\nPermission is hereby granted ..."

const dirs = []
after(() => dirs.forEach((dir) => rmSync(dir, { recursive: true, force: true })))
/** A scratch folder holding files (path -> text, or an object written as JSON). */
function tree(files) {
  const dir = mkdtempSync(path.join(tmpdir(), "cake-notices-"))
  dirs.push(dir)
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, name)), { recursive: true })
    writeFileSync(path.join(dir, name), typeof content === "string" ? content : JSON.stringify(content))
  }
  return dir
}
/** An output bundle with one chunk of these modules (id -> rendered length) and these assets. */
function bundle(modules, assets = []) {
  const chunk = { type: "chunk", modules: Object.fromEntries(Object.entries(modules).map(([id, length]) => [id, { renderedLength: length }])) }
  return { "assets/main.js": chunk, ...Object.fromEntries(assets.map((asset, n) => [`asset${n}`, { type: "asset", ...asset }])) }
}
const settings = (packages = {}, entries = []) => ({ ...SETTINGS, texts: { packages }, files: { entries } })
const names = (packages) => packages.map((pkg) => `${pkg.name}@${pkg.version}`).sort()

test("a module belongs to the nearest package.json with a name, not to a dist/package.json that only sets the type", () => {
  const root = tree({
    "node_modules/@scope/kit/package.json": { name: "@scope/kit", version: "1.0.0", license: "MIT" },
    "node_modules/@scope/kit/dist/package.json": { type: "module" },
    "node_modules/@scope/kit/dist/esm/index.js": "export {}",
  })
  const pkg = packageOf(path.join(root, "node_modules/@scope/kit/dist/esm/index.js"))
  assert.equal(`${pkg.name}@${pkg.version}`, "@scope/kit@1.0.0")
  assert.equal(pkg.dir, path.join(root, "node_modules/@scope/kit"))
})

test("licence and notice files are found by name in any case and spelling; other files and folders are not", () => {
  const dir = tree({ "LICENSE-MIT": "x", "licence.md": "x", "NOTICE": "x", "COPYING.txt": "x", "README.md": "x", "license/inner.txt": "x" })
  assert.deepEqual(licenceFiles(dir, SETTINGS.licence_files.prefixes), ["COPYING.txt", "LICENSE-MIT", "NOTICE", "licence.md"])
})

test("the declared licence is read from the SPDX field and from the older object and list forms", () => {
  assert.equal(declaredLicence({ license: " MIT " }), "MIT")
  assert.equal(declaredLicence({ license: { type: "ISC" } }), "ISC")
  assert.equal(declaredLicence({ licenses: [{ type: "MIT" }, { type: "Apache-2.0" }] }), "MIT OR Apache-2.0")
  assert.equal(declaredLicence({}), "")
})

test("licence texts are copied with \\n line ends and without a byte order mark or trailing blank lines", () => {
  const dir = tree({ LICENSE: "﻿MIT License\r\n\r\nCopyright (c) A\r\n\r\n" })
  assert.equal(readText(path.join(dir, "LICENSE")), "MIT License\n\nCopyright (c) A")
})

test("bundled packages: code that was rendered and styles a stylesheet imports; not virtual or fully removed modules", () => {
  const root = tree({
    "node_modules/used/package.json": { name: "used", version: "1.0.0" },
    "node_modules/used/index.js": "export const a = 1",
    "node_modules/shaken/package.json": { name: "shaken", version: "2.0.0" },
    "node_modules/shaken/index.js": "export const b = 2",
    "node_modules/twcss/package.json": { name: "twcss", version: "4.0.0", style: "index.css" },
    "node_modules/twcss/index.css": "@import './theme.css';\n",
    "node_modules/twcss/theme.css": "@import \"nested-styles\";\n",
    "node_modules/nested-styles/package.json": { name: "nested-styles", version: "0.1.0", exports: { ".": { style: "./dist/a.css" } } },
    "node_modules/nested-styles/dist/a.css": ".a{}",
    "node_modules/@ui/kit/package.json": { name: "@ui/kit", version: "3.1.0", exports: { "./tailwind.css": "./dist/tailwind.css" } },
    "node_modules/@ui/kit/dist/tailwind.css": ".b{}",
    "src/index.css": "@import \"twcss\";\n@import url('./more.css') layer(base);\n@import \"https://fonts.example.com/x.css\";\n",
    "src/more.css": "@import \"@ui/kit/tailwind.css\";\n",
  })
  const found = bundledPackages(bundle({
    [path.join(root, "node_modules/used/index.js") + "?commonjs-es-import"]: 10,
    [path.join(root, "node_modules/shaken/index.js")]: 0,
    "\0rolldown/runtime.js": 50,
    [path.join(root, "src/index.css")]: 0,
    [path.join(root, "src/main.js")]: 99,
  }))
  assert.deepEqual(names(found), ["@ui/kit@3.1.0", "nested-styles@0.1.0", "twcss@4.0.0", "used@1.0.0"])
})

test("a file of notices.json \"files\" is listed only when the build put it into dist/", () => {
  const entries = [
    { file: "src/assets/fonts/A.ttf", license: "OFL-1.1", licence_file: "src/assets/fonts/A-OFL.txt" },
    { file: "src/assets/fonts/B.ttf", license: "OFL-1.1", licence_file: "src/assets/fonts/B-OFL.txt" },
  ]
  const output = bundle({}, [{ fileName: "assets/A-x1.ttf", originalFileNames: ["src/assets/fonts/A.ttf"] }])
  assert.deepEqual(bundledFiles(output, "/web", entries), [entries[0]])
})

/** Packages as bundledPackages gives them, from a scratch node_modules: name -> {version, files, license}. */
function packages(spec) {
  const files = {}
  for (const [name, { version, license = "MIT", files: own = {} }] of Object.entries(spec)) {
    files[`node_modules/${name}/package.json`] = { name, version, license }
    for (const [file, text] of Object.entries(own)) files[`node_modules/${name}/${file}`] = text
  }
  const root = tree(files)
  return { root, list: Object.keys(spec).map((name) => packageOf(path.join(root, "node_modules", name, "package.json"))) }
}

test("each package's licence and notice files are copied whole, packages sorted by name, then the files", () => {
  const { root, list } = packages({
    zeta: { version: "1.0.0", files: { LICENSE: MIT } },
    "@alpha/one": { version: "2.0.0", license: "Apache-2.0", files: { LICENSE: "Apache License 2.0 ...", NOTICE: "Alpha One\nCopyright 2026 Alpha" } },
  })
  writeFileSync(path.join(root, "OFL.txt"), "Copyright 2016 The Font Project Authors\n\nSIL OPEN FONT LICENSE Version 1.1")
  const font = { file: "Font.ttf", license: "OFL-1.1", licence_file: "OFL.txt" }
  const notices = buildNotices(list, [font], settings({}, [font]), root)
  assert.deepEqual(notices.problems, [])
  assert.deepEqual(notices.entries.map((entry) => entry.title), ["@alpha/one 2.0.0", "zeta 1.0.0", "Font.ttf"])
  assert.ok(notices.text.includes("  @alpha/one 2.0.0 (Apache-2.0)\n  zeta 1.0.0 (MIT)\n  Font.ttf (OFL-1.1)\n"), notices.text)
  assert.ok(notices.text.includes("@alpha/one 2.0.0\nLicense: Apache-2.0\n\n----- LICENSE -----\n\nApache License 2.0 ...\n\n----- NOTICE -----\n\nAlpha One\nCopyright 2026 Alpha\n"))
  assert.ok(notices.text.includes("----- OFL.txt -----\n\nCopyright 2016 The Font Project Authors"))
  assert.equal(buildNotices([...list].reverse(), [font], settings({}, [font]), root).text, notices.text, "the order found does not matter")
})

test("a package that ships no licence file stops the build, unless notices.json holds its text for that version", () => {
  const { root, list } = packages({ bare: { version: "2.3.8" } })
  assert.match(buildNotices(list, [], settings(), root).problems.join("\n"), /bare 2\.3\.8 ships no licence file/)
  const kept = { bare: { version: "2.3.8", source: "https://example.com/bare/blob/abc123/LICENSE", text: MIT + "\n" } }
  const notices = buildNotices(list, [], settings(kept), root)
  assert.deepEqual(notices.problems, [])
  assert.ok(notices.text.includes(`----- LICENSE (not in the npm package; from https://example.com/bare/blob/abc123/LICENSE) -----\n\n${MIT}\n`))
})

test("a text in notices.json that is out of date stops the build: another version, a licence file now, or not bundled", () => {
  const { root, list } = packages({ bare: { version: "2.4.0" }, grown: { version: "1.0.0", files: { LICENSE: MIT } } })
  const text = (version) => ({ version, source: "https://example.com/x", text: MIT })
  const problems = buildNotices(list, [], settings({ bare: text("2.3.8"), grown: text("1.0.0"), gone: text("1.0.0") }), root).problems
  assert.equal(problems.length, 3, problems.join("\n"))
  assert.match(problems.join("\n"), /bare 2\.4\.0: notices\.json "texts" has its licence for 2\.3\.8/)
  assert.match(problems.join("\n"), /grown 1\.0\.0 ships its own licence file now/)
  assert.match(problems.join("\n"), /gone is no longer bundled/)
})

test("a file of notices.json \"files\" whose licence file is missing stops the build", () => {
  const root = tree({})
  const font = { file: "Font.ttf", license: "OFL-1.1", licence_file: "Font-OFL.txt" }
  assert.match(buildNotices([], [font], settings({}, [font]), root).problems.join("\n"), /Font\.ttf: its licence file Font-OFL\.txt is missing/)
})

// The real build, checked against what a separate probe sees in the same bundle: the package of every node_modules
// module with rendered code (by its path) and every package src/index.css imports.
const PACKAGE_IN_PATH = /[\\/]node_modules[\\/]((?:@[^\\/]+[\\/])?[^\\/]+)[\\/](?!.*[\\/]node_modules[\\/])/
const BARE_IMPORT = /@import\s+["']([^"'./][^"']*)["']/g

test("the build writes the notices into dist/: every bundled package and font with its licence text, nothing else", async () => {
  const out = mkdtempSync(path.join(tmpdir(), "cake-notices-build-"))
  dirs.push(out)
  const seen = new Set()
  const probe = {
    name: "probe-bundled-packages",
    generateBundle(_, output) {
      for (const chunk of Object.values(output)) {
        if (chunk.type !== "chunk") continue
        for (const [id, module] of Object.entries(chunk.modules)) {
          const match = module.renderedLength > 0 && id.match(PACKAGE_IN_PATH)
          if (match) seen.add(match[1].replace(/\\/g, "/"))
        }
      }
    },
  }
  await build({ root: web, configFile: path.join(web, "vite.config.ts"), logLevel: "silent", plugins: [probe], build: { outDir: out, emptyOutDir: true } })
  for (const [, specifier] of readFileSync(path.join(web, "src", "index.css"), "utf8").matchAll(BARE_IMPORT)) {
    seen.add(specifier.split("/").slice(0, specifier.startsWith("@") ? 2 : 1).join("/"))
  }
  const text = readFileSync(path.join(out, SETTINGS.file), "utf8")
  const index = text.split(`\n${ENTRY_RULE}\n`)[0].split("\n").filter((line) => line.startsWith("  ")).map((line) => line.trim())
  const titles = index.map((line) => line.replace(/ \(.*\)$/, "")) // "name version", or a file's name
  const fileTitles = SETTINGS.files.entries.map((entry) => path.basename(entry.file))
  const packageNames = new Set(titles.filter((title) => !fileTitles.includes(title)).map((title) => title.replace(/ [^ ]+$/, "")))
  assert.ok(seen.has("react") && seen.has("tailwindcss"), `the probe saw ${[...seen].join(", ")}`)
  assert.deepEqual([...packageNames].sort(), [...seen].sort(), "every bundled package is listed, and nothing else")
  for (const font of readdirSync(path.join(out, "assets")).filter((name) => name.endsWith(".ttf"))) {
    assert.ok(fileTitles.some((title) => titles.includes(title) && font.startsWith(title.replace(/\.ttf$/, "-"))), font)
  }
  for (const title of titles) {
    const entry = text.split(`\n${ENTRY_RULE}\n${title}\nLicense: `)[1]
    assert.ok(entry, `${title} has no entry`)
    assert.match(entry.split(`\n${ENTRY_RULE}\n`)[0], /\n----- .+ -----\n\n *\S/, `${title} has no licence text`)
  }
})
