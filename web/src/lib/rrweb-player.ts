// rrweb-player 2.0.0-alpha.18 (MIT, THIRD_PARTY.md), loaded at run time from the two files cake serves under /static/
// (agentcake/assets.py): the pages bundle no copy of it and add no npm dependency, and every replay opened in a
// visit shares one load. The script is rrweb-player's UMD build, which puts `rrwebPlayer` on window. Only what the
// replay page uses is typed here; rrweb's own docs cover the rest (github.com/rrweb-io/rrweb, packages/rrweb-player).
import type { ReplayEvent } from "@/data/types"

/** Relative to the page, like the API (api/…), so the pages work under any path. */
const SCRIPT = "static/rrweb-player.umd.cjs"
const STYLES = "static/rrweb-player.css"

/** rrweb's Replayer, inside the player: what plays the events. Times are milliseconds from its first event. */
export type Replayer = {
  play(offsetMs?: number): void
  pause(offsetMs?: number): void
  getCurrentTime(): number
  setConfig(config: { speed?: number; mouseTail?: MouseTail }): void
  on(event: "finish" | "resize" | "fullsnapshot-rebuilded", handler: () => void): void
  addEvent(event: ReplayEvent): void
  readonly wrapper: HTMLElement
}
/** The trail the cursor leaves; its colour comes from a token (use-replay.ts reads it from the page). */
export type MouseTail = { strokeStyle: string }

export type PlayerProps = {
  events: ReplayEvent[]
  width: number
  height: number
  autoPlay: boolean
  showController: boolean
  skipInactive: boolean
  speedOption: number[]
  speed: number
  mouseTail: MouseTail
}
/** rrweb-player's Svelte component: the frame that scales the replay into width × height. */
export type Player = {
  getReplayer(): Replayer
  triggerResize(): void
  $set(props: Partial<Pick<PlayerProps, "width" | "height">>): void
  $destroy(): void
}
type PlayerClass = new (options: { target: HTMLElement; props: PlayerProps }) => Player

let loading: Promise<PlayerClass> | null = null

/** rrweb-player's class, once its script and stylesheet are in. A failed load can be tried again. */
export function loadPlayer(): Promise<PlayerClass> {
  loading ??= new Promise<PlayerClass>((resolve, reject) => {
    const styles = Object.assign(document.createElement("link"), { rel: "stylesheet", href: STYLES })
    // First in <head>, so the theme's rules for the player (index.css, "Replay player") come later and win.
    document.head.prepend(styles)
    const script = Object.assign(document.createElement("script"), { src: SCRIPT, async: true })
    const fail = () => { loading = null; script.remove(); styles.remove(); reject(new Error("The replay player didn't load. Reload the page.")) }
    script.onerror = fail
    script.onload = () => {
      const Player = (window as Window & { rrwebPlayer?: { Player?: PlayerClass } }).rrwebPlayer?.Player
      if (Player) resolve(Player)
      else fail()
    }
    document.head.append(script)
  })
  return loading
}
