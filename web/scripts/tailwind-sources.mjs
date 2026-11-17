// The files Tailwind reads for class names, found by the two calls its Vite plugin makes: compile() reads the
// stylesheet's source(…) and @source rules, and the Scanner lists the files they match. check:ui requires that these are
// the pages' own code only (src, .ts and .tsx; DESIGN.md §12): any other file under web/ (a script, a test, a sample
// answer, a licence text) would add a rule no page uses to the CSS that ships, for every word in it that reads as a
// class name.
import { readFileSync, realpathSync } from "node:fs"
import { createRequire } from "node:module"
import path from "node:path"
import { pathToFileURL } from "node:url"

// the compiler and the scanner the build uses: the Vite plugin's own, found from where the plugin is installed
const plugin = createRequire(createRequire(import.meta.url).resolve("@tailwindcss/vite"))
const load = (name) => import(pathToFileURL(plugin.resolve(name)).href)

/** The files Tailwind reads for a stylesheet's class names. base: the folder the build runs in, which Tailwind reads
 *  whole when the stylesheet names no source of its own. */
export async function tailwindFiles(stylesheet, base) {
  const [{ compile }, { Scanner }] = await Promise.all([load("@tailwindcss/node"), load("@tailwindcss/oxide")])
  const compiler = await compile(readFileSync(stylesheet, "utf8"), { base: path.dirname(stylesheet), from: stylesheet, onDependency: () => {} })
  const root = compiler.root === "none" ? [] : [compiler.root ? { ...compiler.root, negated: false } : { base, pattern: "**/*", negated: false }]
  const scanner = new Scanner({ sources: [...root, ...compiler.sources] })
  scanner.scan()
  return scanner.files
}

/** The files among them that are not the pages' code (a .ts or .tsx file inside src). The scanner gives real paths, so
 *  src is compared as its real path too. */
export function notPageCode(files, src) {
  const code = realpathSync(src)
  return files.filter((f) => path.relative(code, f).startsWith("..") || !/\.tsx?$/.test(f))
}
