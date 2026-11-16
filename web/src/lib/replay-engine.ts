// Plays one session's replay on the session's own clock: rrweb-player (./rrweb-player.ts) fed chunk by chunk
// (./chunk-feed.ts). It starts with the chunks the start moment needs plus the next one, reads each next chunk as
// playback enters the one before it, reads every chunk before a moment it jumps to, and waits (then goes on) if
// playback ever gets ahead of what has arrived. The cursor carries the name of who acted at that moment (data-who,
// data-label on rrweb's cursor; index.css draws the label in token colours). use-replay.ts wraps it for React.
import type { Actor, ReplayChunk, ReplayEvent, SessionDetail } from "@/data/types"
import { ChunkFeed } from "./chunk-feed"
import { actorAt, addressAt, clampMs, firstPageIn, lastChunkFor, pagesIn, type PageAt } from "./replay-timing"
import { loadPlayer, type Player, type Replayer } from "./rrweb-player"

/** The playback speeds offered (the first is where it starts). */
export const SPEEDS = [1, 2, 4]
/** rrweb's Replayer needs a page's Meta event and its full snapshot before it can show anything. */
const MIN_EVENTS = 2
/** The token each actor's cursor trail is drawn in (a canvas needs the colour itself, read from the page). */
const TRAIL_TOKEN: Record<Actor, string> = { human: "--human", agent: "--agent", unsure: "--unsure" }

export type EngineUpdates = {
  time(ms: number): void
  playing(on: boolean): void
  waiting(on: boolean): void
  address(href: string): void
  /** Whether the player has a page to show at the playhead (false: only the pointer and the clicks). */
  page(shown: boolean): void
  failed(error: unknown): void
}
type Options = {
  el: HTMLElement
  detail: SessionDetail
  /** The cursor's label for each actor ("Claude in Chrome", "A human", "Unknown"). */
  labels: Record<Actor, string>
  fetchChunk(n: number): Promise<ReplayChunk>
  on: EngineUpdates
}

/** The replayer takes added events a moment later (rrweb queues them as a microtask); wait for that. */
const afterAdded = () => new Promise((resolve) => setTimeout(resolve, 0))

export class ReplayEngine {
  private readonly o: Options
  private readonly feed: ChunkFeed
  private collected: ReplayEvent[] = [] // events that arrive before the player exists
  private pages: PageAt[] = []
  private player: Player | null = null
  private replayer: Replayer | null = null
  private baseMs = 0 // the session moment of the replayer's first event: its time 0
  private endMs = 0 // the session moment of the last event handed over
  private wanted = -1 // the last chunk asked for
  private wantPlaying = false
  private seeks = 0
  private frame = 0
  private who: Actor | undefined | null = null // null: not drawn yet
  private firstPageMs = Infinity // from this moment on the player has a page to show; -Infinity: from the start
  private pageShown: boolean | null = null // null: not said yet
  private destroyed = false

  constructor(options: Options) {
    this.o = options
    this.feed = new ChunkFeed(options.detail.replay.chunks.length, options.fetchChunk, (events) => this.collect(events))
  }

  private get replay() { return this.o.detail.replay }
  private get durationMs() { return this.o.detail.timeline.duration_ms }

  /** Loads the player and the first chunks, and shows the start moment, paused. */
  async start() {
    const Player = await loadPlayer()
    await this.ask(lastChunkFor(this.replay.chunks, this.replay.start_ms))
    while (this.collected.length < MIN_EVENTS && !this.feed.complete) await this.ask(this.feed.handedOver)
    if (this.destroyed) return
    if (this.collected.length < MIN_EVENTS) throw new Error("This replay has too little content to play. Try opening another session.")
    this.baseMs = this.collected[0].timestamp - this.replay.epoch_ms
    const { clientWidth: width, clientHeight: height } = this.o.el
    this.player = new Player({ target: this.o.el, props: { events: this.collected, width, height, autoPlay: false, showController: false,
      skipInactive: false, speedOption: SPEEDS, speed: SPEEDS[0], mouseTail: this.trail(undefined) } })
    this.replayer = this.player.getReplayer()
    this.collected = []
    this.feed.handTo((events) => this.give(events))
    this.replayer.on("finish", () => this.finished())
    this.replayer.on("resize", () => this.unscale())
    this.unscale()
    await this.seek(this.replay.start_ms, false)
  }

  play() {
    const at = this.now()
    const ended = this.feed.complete && at >= this.endMs
    void this.seek(ended ? this.baseMs : at, true)
  }

  pause() {
    this.wantPlaying = false
    this.seeks += 1 // a jump still on its way must not start playing again
    this.replayer?.pause()
    this.stopClock()
    this.o.on.playing(false)
    this.show(this.now())
  }

  setSpeed(speed: number) {
    this.replayer?.setConfig({ speed })
  }

  /** Shows a moment (and plays on from it when `play`): first reads every chunk it needs, then moves the player. */
  async seek(ms: number, play = this.wantPlaying) {
    const target = clampMs(ms, this.durationMs), mine = ++this.seeks
    this.show(target)
    try {
      await this.ask(lastChunkFor(this.replay.chunks, target))
      await afterAdded()
    } catch (error) {
      if (mine === this.seeks && !this.destroyed) this.o.on.failed(error)
      return
    }
    if (mine !== this.seeks || !this.replayer || this.destroyed) return
    const offset = Math.max(0, target - this.baseMs)
    this.wantPlaying = play
    if (play) { this.replayer.play(offset); this.startClock() } else { this.replayer.pause(offset); this.stopClock() }
    this.o.on.playing(play)
    this.show(target)
  }

  /** The player keeps the stage's size (called when the stage changes size). */
  resize() {
    if (!this.player) return
    this.player.$set({ width: this.o.el.clientWidth, height: this.o.el.clientHeight })
    this.player.triggerResize()
    this.unscale()
  }

  destroy() {
    this.destroyed = true
    this.stopClock()
    this.player?.$destroy()
    this.player = this.replayer = null
  }

  /** Where the player is, on the session's clock. */
  private now() {
    return this.replayer ? clampMs(this.replayer.getCurrentTime() + this.baseMs, this.durationMs) : this.replay.start_ms
  }

  private ask(last: number) {
    this.wanted = Math.max(this.wanted, last)
    return this.feed.through(last)
  }

  private collect(events: ReplayEvent[]) {
    this.collected.push(...events)
    // the replayer builds the first page it starts with straight away, whatever that page's moment
    if (firstPageIn(events, this.replay.epoch_ms) !== Infinity) this.firstPageMs = -Infinity
    this.note(events)
  }

  private give(events: ReplayEvent[]) {
    for (const event of events) this.replayer?.addEvent(event)
    this.firstPageMs = Math.min(this.firstPageMs, firstPageIn(events, this.replay.epoch_ms))
    this.note(events)
  }

  private note(events: ReplayEvent[]) {
    this.pages.push(...pagesIn(events, this.replay.epoch_ms))
    if (events.length) this.endMs = Math.max(this.endMs, events[events.length - 1].timestamp - this.replay.epoch_ms)
  }

  /** The time, the page's address and the cursor's owner for a moment. */
  private show(ms: number) {
    this.o.on.time(ms)
    this.o.on.address(addressAt(this.pages, ms, this.replay.start_url))
    const paged = ms >= this.firstPageMs
    if (paged !== this.pageShown) { this.pageShown = paged; this.o.on.page(paged) }
    const who = actorAt(this.o.detail.timeline.segments, ms)
    if (who === this.who || !this.replayer) return
    this.who = who
    const cursor = this.replayer.wrapper.querySelector<HTMLElement>(".replayer-mouse")
    if (cursor) Object.assign(cursor.dataset, { who: who ?? "", label: who ? this.o.labels[who] : "" })
    this.replayer.setConfig({ mouseTail: this.trail(who) })
  }

  private trail(who: Actor | undefined) {
    return { strokeStyle: getComputedStyle(this.o.el).getPropertyValue(TRAIL_TOKEN[who ?? "unsure"]).trim() }
  }

  /** The cursor's label keeps its size whatever the player's scale (--replay-unscale, index.css). */
  private unscale() {
    const wrapper = this.replayer?.wrapper
    const shown = wrapper?.getBoundingClientRect().width
    if (wrapper?.offsetWidth && shown) this.o.el.style.setProperty("--replay-unscale", String(wrapper.offsetWidth / shown))
  }

  private startClock() {
    this.stopClock()
    const tick = () => {
      const ms = this.now()
      this.show(ms)
      const last = lastChunkFor(this.replay.chunks, ms)
      if (last > this.wanted) this.ask(last).catch((error: unknown) => this.o.on.failed(error))
      this.frame = requestAnimationFrame(tick)
    }
    this.frame = requestAnimationFrame(tick)
  }

  private stopClock() {
    cancelAnimationFrame(this.frame)
  }

  /** The replayer ran out of events: the replay's end, or playback got ahead of the chunks (wait, then go on). */
  private finished() {
    const at = this.now()
    if (this.feed.complete || !this.wantPlaying) {
      this.wantPlaying = false
      this.stopClock()
      this.o.on.playing(false)
      this.show(this.feed.complete ? this.endMs : at)
      return
    }
    this.o.on.waiting(true)
    const mine = this.seeks
    this.ask(this.feed.handedOver).then(afterAdded).then(() => {
      if (mine === this.seeks && this.wantPlaying && this.replayer) this.replayer.play(Math.max(0, at - this.baseMs))
    }, (error: unknown) => this.o.on.failed(error)).finally(() => this.o.on.waiting(false))
  }
}
