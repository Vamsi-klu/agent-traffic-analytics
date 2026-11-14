"use strict"
/*
 * cross-check.js — the Node half of the cross-language check in tests/test_edge_vectors.py: cake's Python makes tokens
 * for many requests, and this script says, for each, what the Node middleware makes for the same request and what it
 * concludes about Python's token.
 *
 *   input (stdin):   [{ secret, request: { method, path, headers }, now_ms, id, client_ip, verdict, version, token }]
 *   output (stdout): [{ token: Node's token or null, result: "ok" | "stale" | "bad" | null (no token to read) }]
 *
 * Step S4.1.
 */
const { mintToken, verifyToken } = require("..")

async function main() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  const cases = JSON.parse(Buffer.concat(chunks).toString("utf8"))
  const out = []
  for (const each of cases) {
    const extras = { nowMs: each.now_ms, id: each.id, ip: each.client_ip, verdict: each.verdict, version: each.version }
    const token = await mintToken(each.secret, each.request, extras)
    const result = each.token ? (await verifyToken(each.secret, each.token, { nowMs: each.now_ms })).result : null
    out.push({ token, result })
  }
  process.stdout.write(JSON.stringify(out))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
