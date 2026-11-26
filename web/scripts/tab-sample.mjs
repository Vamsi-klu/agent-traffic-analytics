// Writes the sample of a session of two tabs from two recorded samples, for the dev, screenshot, visual and test
// servers (DESIGN.md §6.4): Tab 1 is session 7f3a-c1 as recorded (a human, Claude in Chrome from 0:38, the human
// again), Tab 2 session 6e0f-13 (the Codex in-app browser in the shop) moved to open 20 s into it, as if that agent
// had worked in a second tab meanwhile. The replays stay what cake.js recorded: Tab 1 plays replay/7f3a-c1/ as it is,
// Tab 2 replay/a1b8-20/, 6e0f-13's events moved by the same 20 s on the session's clock. Everything else is put together
// the way the API does it for a session of several tabs (agentcake/api/session_tabs.py, rows.py): pages, actions and the
// server half of both tabs in time order with their tab, each tab's own verdict, reasons and track, the verdict resting
// on the surer Agent tab, the hand-off from one tab to the other, the replay following the tab acted in. Tab 2's reasons
// keep the moments of its own recording.
// Usage: node scripts/tab-sample.mjs      (again whenever the two recorded samples change)
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { MOVED } from "./replay-walks.mjs"

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "data", "fixtures")
const read = (name) => JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf8"))
const write = (name, value) => {
  mkdirSync(path.dirname(path.join(fixtures, `${name}.json`)), { recursive: true })
  writeFileSync(path.join(fixtures, `${name}.json`), `${JSON.stringify(value, null, 2)}\n`)
}

const [{ id: SECOND, from: SECOND_FROM, session: SESSION }] = MOVED // the second tab, its walk, and the sample session
const OPENS_AT_MS = 20_000 // when the second tab opens, on the session's clock
const WHEN = "Yesterday 14:40" // when the session began, as the list writes it (its row is the last of sessions.json)
// Who acted, as the API titles these turns in time order, each agent's turn by its own agent: the human in Tab 1, the
// Codex in-app browser in Tab 2 from 0:22, Claude in Chrome in Tab 1 from 0:38, the human again (session.title).
const TITLE = "A human, then Codex in-app browser, then Claude in Chrome, then the human again"
const first = read("session"), second = read(`session/${SECOND_FROM}`)
const move = (ms) => ms + OPENS_AT_MS
const shift = first.replay.epoch_ms + OPENS_AT_MS - second.replay.epoch_ms // epoch ms the second tab's events move by
const length = Math.max(first.timeline.duration_ms, move(second.timeline.duration_ms))
const byTime = (key) => (a, b) => a[key] - b[key]

const secondSegments = second.timeline.segments.map((s) => ({ ...s, start_ms: move(s.start_ms), end_ms: move(s.end_ms) }))
const secondChunks = second.replay.chunks.map((c) => ({ start_ms: move(c.start_ms), end_ms: move(c.end_ms) }))
// The agent's first run in the second tab follows the human's in the first: a hand-off from one tab to the other.
const crossing = { at_ms: secondSegments.find((s) => s.who === "agent").start_ms, to: "agent" }

/** Each actor's share of the actions both tabs list (their page opens left out), whole percents adding up to 100. */
function share(actions) {
  const taken = actions.filter((a) => !a.what.startsWith("Open "))
  const counts = ["human", "agent", "unsure"].map((who) => taken.filter((a) => a.who === who).length)
  const exact = counts.map((n) => (n * 100) / taken.length), whole = exact.map(Math.floor)
  const order = exact.map((e, i) => [whole[i] - e, i]).sort((a, b) => a[0] - b[0]).map(([, i]) => i)
  for (const i of order.slice(0, 100 - whole.reduce((a, b) => a + b, 0))) whole[i] += 1
  return { human: whole[0], agent: whole[1], unsure: whole[2] }
}

const actions = [...first.actions.map((a) => ({ ...a, tab: 1 })), ...second.actions.map((a) => ({ ...a, at_ms: move(a.at_ms), tab: 2 }))].sort(byTime("at_ms"))
const pages = [...first.pages.map((p) => ({ ...p, tab: 1 })), ...second.pages.map((p) => ({ ...p, at_ms: move(p.at_ms), tab: 2 }))].sort(byTime("at_ms"))
const tabReplay = (r, chunks, start) => ({ start_ms: start, start_url: r.start_url, chunks, missing: r.missing })
const summary = {
  ...first.session, id: SESSION, when: WHEN, duration_ms: length, pages: pages.length, share: share(actions),
  tabs: [{ start_ms: 0, end_ms: first.timeline.duration_ms, segments: first.timeline.segments },
    { start_ms: OPENS_AT_MS, end_ms: move(second.timeline.duration_ms), segments: secondSegments }],
  agents: [{ name: first.session.agent, certainty: first.session.certainty }, { name: second.session.agent, certainty: second.session.certainty }],
}
delete summary.segments
write(`session/${SESSION}`, {
  session: summary, title: TITLE, summary: first.summary, percent: first.percent,
  timeline: { duration_ms: length, segments: [...first.timeline.segments, ...secondSegments].sort(byTime("start_ms")), handoffs: [...first.timeline.handoffs, crossing].sort(byTime("at_ms")) },
  pages, layers: first.layers, actions, replay: first.replay,
  server: { pages: [...first.server.pages.map((p) => ({ ...p, tab: 1 })), ...second.server.pages.map((p) => ({ ...p, at_ms: move(p.at_ms), tab: 2 }))].sort(byTime("at_ms")),
    network: first.server.network, note: null },
  tabs: [
    { id: first.session.id, tab: 1, start_ms: 0, end_ms: first.timeline.duration_ms, verdict: first.session.verdict, evidence: first.session.evidence,
      agent_turns: first.session.agent_turns, agent: first.session.agent, certainty: first.session.certainty, percent: first.percent,
      summary: first.summary, layers: first.layers, segments: first.timeline.segments, handoffs: first.timeline.handoffs,
      replay: tabReplay(first.replay, first.replay.chunks, first.replay.start_ms) },
    { id: SECOND, tab: 2, start_ms: OPENS_AT_MS, end_ms: move(second.timeline.duration_ms), verdict: second.session.verdict, evidence: second.session.evidence,
      agent_turns: second.session.agent_turns, agent: second.session.agent, certainty: second.session.certainty, percent: second.percent,
      summary: second.summary, layers: second.layers, segments: secondSegments, handoffs: [crossing],
      replay: tabReplay(second.replay, secondChunks, move(second.replay.start_ms)) },
  ],
  // the second tab while the agent there is the one acting, the first tab before and after
  follow: [{ tab: first.session.id, start_ms: 0, end_ms: OPENS_AT_MS }, { tab: SECOND, start_ms: OPENS_AT_MS, end_ms: move(second.timeline.duration_ms) },
    { tab: first.session.id, start_ms: move(second.timeline.duration_ms), end_ms: length }],
  verdict_tab: first.session.id,
})
second.replay.chunks.forEach((_, n) => {
  const chunk = read(`replay/${SECOND_FROM}/${n}`)
  write(`replay/${SECOND}/${n}`, { chunk: n, start_ms: move(chunk.start_ms), end_ms: move(chunk.end_ms),
    events: chunk.events.map((e) => ({ ...e, timestamp: e.timestamp + shift })) })
})
console.log(`session/${SESSION}.json and replay/${SECOND}/ (${second.replay.chunks.length} chunks) written`)
