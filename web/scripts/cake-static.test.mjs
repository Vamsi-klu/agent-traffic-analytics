// Tests for the replay player's files on the dev, preview, screenshot and test servers: the two files cake
// serves under /static/, with script and stylesheet types; anything else goes on. Usage: node --test scripts/
import assert from "node:assert/strict"
import { createServer } from "node:http"
import { after, before, test } from "node:test"
import { cakeStatic } from "./cake-static.mjs"

let server, base
before(async () => {
  const handle = cakeStatic()
  server = createServer((req, res) => handle(req, res, () => { res.statusCode = 418; res.end() }))
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve))
  base = `http://127.0.0.1:${server.address().port}`
})
after(() => server.close())

test("the player's script and stylesheet come from agentcake/static with their types", async () => {
  const script = await fetch(`${base}/static/rrweb-player.umd.cjs`)
  assert.equal(script.status, 200)
  assert.match(script.headers.get("content-type"), /^text\/javascript/)
  assert.match(await script.text(), /rrwebPlayer/)
  const styles = await fetch(`${base}/static/rrweb-player.css`)
  assert.equal(styles.status, 200)
  assert.match(styles.headers.get("content-type"), /^text\/css/)
  assert.match(await styles.text(), /\.replayer-mouse/)
})

test("any other path goes on to the next handler, cake's other static files included", async () => {
  for (const pathname of ["/static/cake.js", "/static/../agentcake/api.py", "/index.html"]) assert.equal((await fetch(base + pathname)).status, 418, pathname)
})
