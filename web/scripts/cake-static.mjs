// The replay player's two files, which cake serves under /static/ (agentcake/assets.py): rrweb-player
// 2.0.0-alpha.18 (MIT, THIRD_PARTY.md), read from agentcake/static/. The pages load them at run time instead of
// bundling an npm copy, so the dev, preview, screenshot and test servers answer the same two paths from the same
// files. A connect-style handler like fixture-api.mjs: anything else goes to next().
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

const STATIC_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "agentcake", "static")
export const PLAYER_FILES = { "/static/rrweb-player.umd.cjs": "text/javascript", "/static/rrweb-player.css": "text/css" }

export function cakeStatic() {
  return async function handle(req, res, next) {
    const pathname = new URL(req.url, "http://static").pathname
    const type = PLAYER_FILES[pathname]
    if (!type) return next?.()
    try {
      const body = await readFile(path.join(STATIC_DIR, path.basename(pathname)))
      res.writeHead(200, { "content-type": `${type}; charset=utf-8` })
      res.end(body)
    } catch (error) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" })
      res.end(`${pathname}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
}
