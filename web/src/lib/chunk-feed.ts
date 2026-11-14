// Reads a replay's chunks as the player needs them (S5.4) and hands their events over strictly in chunk order, however
// the answers arrive: rrweb rebuilds a page from its last full snapshot onwards, so chunk n is no use before chunks
// 0 … n-1. Chunks can be asked for together (a jump far ahead asks for all the chunks before it at once); each is
// asked for once, and one that failed is asked for again next time.
import type { ReplayChunk, ReplayEvent } from "@/data/types"

export type FetchChunk = (n: number) => Promise<ReplayChunk>
export type TakeEvents = (events: ReplayEvent[]) => void

export class ChunkFeed {
  private readonly asked = new Map<number, Promise<void>>()
  private readonly arrived = new Map<number, ReplayEvent[]>()
  private next = 0 // the first chunk not handed over yet
  private readonly count: number
  private readonly fetchChunk: FetchChunk
  private take: TakeEvents

  constructor(count: number, fetchChunk: FetchChunk, take: TakeEvents) {
    this.count = count
    this.fetchChunk = fetchChunk
    this.take = take
  }

  /** Where events go from now on (before the player exists they are collected, then given to the player). */
  handTo(take: TakeEvents) {
    this.take = take
  }

  /** How many chunks have been handed over: 0 … handedOver-1. */
  get handedOver() {
    return this.next
  }

  /** Every chunk has been handed over. */
  get complete() {
    return this.next >= this.count
  }

  /** Asks for chunks 0 … last that weren't asked for yet; resolves once all of them are handed over. */
  async through(last: number): Promise<void> {
    const waits: Promise<void>[] = []
    for (let n = 0; n <= Math.min(last, this.count - 1); n++) {
      if (n < this.next) continue
      let wait = this.asked.get(n)
      if (!wait) {
        wait = this.fetchChunk(n).then(
          (chunk) => { this.arrived.set(n, chunk.events); this.handOver() },
          (error: unknown) => { this.asked.delete(n); throw error },
        )
        this.asked.set(n, wait)
      }
      waits.push(wait)
    }
    await Promise.all(waits)
  }

  private handOver() {
    for (let events = this.arrived.get(this.next); events; events = this.arrived.get(this.next)) {
      this.arrived.delete(this.next)
      this.next += 1
      this.take(events)
    }
  }
}
