// Tests for the recorded sample replays: they are what scripts/replay-fixtures.mjs promises, checked without
// recording again. Every chunk is one window of cake's chunk length, in time order, as the session's sample lists it;
// the first chunk lets the player start (a page's address, then its full snapshot) at the default address; nothing
// typed, no card number, no site key but the placeholder. Usage: node --test scripts/   (npm test)
import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import { test } from "node:test"
import { CONTRACT } from "./check-schemas.mjs"
import { DEFAULT_PORT, RRWEB, SITE_KEY_PLACEHOLDER, chunksOf, forbidden, serverPage } from "./replay-samples.mjs"
import { MOVED, TYPED, WALKS } from "./replay-walks.mjs"

const fixtures = CONTRACT.fixtureDir
const text = (rel) => readFileSync(path.join(fixtures, rel), "utf8")
const read = (rel) => JSON.parse(text(rel))
const sampleOf = (id) => { const main = read("session.json"); return main.session.id === id ? main : read(`session/${id}.json`) }
const chunkNumbers = (id) => readdirSync(path.join(fixtures, "replay", id)).map((f) => Number(f.slice(0, -".json".length))).sort((a, b) => a - b)
const withoutEvents = ({ events, ...head }) => head

test("every walk has a recorded replay, and every replay has a walk or is one moved in time", () => {
  assert.deepEqual(readdirSync(path.join(fixtures, "replay")).sort(), [...WALKS, ...MOVED].map((w) => w.id).sort())
})

for (const moved of MOVED) {
  test(`${moved.id}: the ${moved.from} walk's replay moved in time, chunk for chunk, as its tab's sample lists them`, () => {
    const chunks = chunkNumbers(moved.id).map((n) => read(`replay/${moved.id}/${n}.json`))
    const from = chunkNumbers(moved.from).map((n) => read(`replay/${moved.from}/${n}.json`))
    const tab = read(`session/${moved.session}.json`).tabs.find((t) => t.id === moved.id)
    assert.deepEqual(chunks.map(({ start_ms, end_ms }) => ({ start_ms, end_ms })), tab.replay.chunks)
    const shift = chunks[0].events[0].timestamp - from[0].events[0].timestamp
    assert.deepEqual(chunks.map((c) => c.events), from.map((c) => c.events.map((e) => ({ ...e, timestamp: e.timestamp + shift }))))
  })
}

for (const walk of WALKS) {
  test(`${walk.id}: the chunks are cake's windows, in time order, as the session's sample lists them`, () => {
    const d = sampleOf(walk.id), chunks = chunkNumbers(walk.id).map((n) => read(`replay/${walk.id}/${n}.json`))
    assert.deepEqual(chunks.map((c) => c.chunk), chunks.map((_, i) => i))
    assert.deepEqual(chunks.map(({ start_ms, end_ms }) => ({ start_ms, end_ms })), d.replay.chunks)
    const events = chunks.flatMap((c) => c.events)
    events.slice(1).forEach((e, i) => assert.ok(e.timestamp >= events[i].timestamp, "events in time order"))
    assert.deepEqual(chunksOf(events, d.replay.epoch_ms).map(withoutEvents), chunks.map(withoutEvents))
    assert.ok(events.at(-1).timestamp - d.replay.epoch_ms <= d.timeline.duration_ms, "nothing after the session's end")
  })

  test(`${walk.id}: the first chunk starts the player (a page's address, then its full snapshot) at the default address`, () => {
    const d = sampleOf(walk.id), [meta, snapshot] = read(`replay/${walk.id}/0.json`).events
    assert.deepEqual([meta.type, snapshot.type], [RRWEB.meta, RRWEB.fullSnapshot])
    assert.equal(new URL(meta.data.href).port, String(DEFAULT_PORT))
    assert.equal(new URL(d.replay.start_url).port, String(DEFAULT_PORT))
  })

  test(`${walk.id}: nothing typed, no card number, and no site key but the placeholder`, () => {
    for (const n of chunkNumbers(walk.id)) {
      const chunk = text(`replay/${walk.id}/${n}.json`)
      assert.equal(forbidden(chunk, TYPED), null, `chunk ${n}`)
      for (const [, key] of chunk.matchAll(/"data-site":"([^"]*)"/g)) assert.equal(key, SITE_KEY_PLACEHOLDER, `chunk ${n}`)
    }
    assert.equal(forbidden(JSON.stringify(sampleOf(walk.id)), TYPED), null, "the session's sample")
  })

  test(`${walk.id}: its stylesheets ask the page's own server for their files, no other address`, () => {
    for (const n of chunkNumbers(walk.id)) assert.doesNotMatch(text(`replay/${walk.id}/${n}.json`), /url\(\\?"?[a-z]+:\/\//i, `chunk ${n}`)
  })
}

test("a server-half row says what cake says of it: each match as true, false or unknown, and its reuses", () => {
  const token = JSON.stringify({ sf: { s: "none", m: "navigate", d: "document", u: "?1" } })
  assert.deepEqual(serverPage([1500, "/demo", token, 1, 0, null, 2], 1000), {
    at_ms: 500, path: "/demo", fetch: { site: "none", mode: "navigate", dest: "document", user: "?1" }, signature: null,
    same_network: true, same_user_agent: false, same_language: null, reuses: 2,
  })
  assert.equal(serverPage([1000, "/", token, null, null, null, null], 1000).reuses, 0)
})
