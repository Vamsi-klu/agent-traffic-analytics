import { readFileSync } from "node:fs"
import path from "node:path"
import { defineConfig, type Plugin } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { cakeStatic } from "./scripts/cake-static.mjs"
import { fixtureApi } from "./scripts/fixture-api.mjs"
import { thirdPartyNotices } from "./scripts/notices.mjs"

/** `npm run dev` and `npm run preview` answer /api from src/data/fixtures (scripts/fixture-api.mjs), and serve the replay
 *  player's files under /static/ (scripts/cake-static.mjs) as cake does. The
 *  build includes none of them: in the release, cake (Python) answers /api and serves /static/. */
function fixtureApiForDev(): Plugin {
  const handlers = () => [fixtureApi(), cakeStatic()]
  return {
    name: "cake-fixture-api",
    configureServer: (server) => { for (const handler of handlers()) server.middlewares.use(handler) },
    configurePreviewServer: (server) => { for (const handler of handlers()) server.middlewares.use(handler) },
  }
}

/** The product's name, from Agent Cake's own data file, the one place it is written: the pages read it as
 *  import.meta.env.VITE_PRODUCT_NAME (src/lib/product.ts) and index.html as %VITE_PRODUCT_NAME% (the browser title). */
const product = JSON.parse(readFileSync(path.resolve(__dirname, "../agentcake/data/product.json"), "utf8"))
/** The names of the session categories and a sentence on each, from the one file the API's words
 *  use too (agentcake/data/judging.en.json): the pages read them as import.meta.env.VITE_TAXONOMY (src/lib/taxonomy.ts). */
const judging = JSON.parse(readFileSync(path.resolve(__dirname, "../agentcake/data/judging.en.json"), "utf8"))
const TAXONOMY_KEYS = ["title", "lead", "verdicts", "unsure", "evidence", "turns", "names"]
const taxonomy = Object.fromEntries(TAXONOMY_KEYS.map((key) => [key, judging[key]]))

// Built to dist/ as static files; cake (Python) serves them and a JSON API. Relative base so it works under any path.
// The build also writes the bundled packages' licence notices into dist/ (scripts/notices.mjs, settings in notices.json).
export default defineConfig({
  base: "./",
  define: { "import.meta.env.VITE_PRODUCT_NAME": JSON.stringify(product.name), "import.meta.env.VITE_TAXONOMY": JSON.stringify(taxonomy) },
  plugins: [react(), tailwindcss(), fixtureApiForDev(), thirdPartyNotices({ root: __dirname, settingsFile: path.resolve(__dirname, "notices.json") })],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    outDir: "dist",
    assetsInlineLimit: 0,
    rolldownOptions: { input: { main: path.resolve(__dirname, "index.html") } },
  },
})
