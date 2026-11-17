// The replay window (DESIGN.md §6): an address bar and the stage rrweb-player draws into (lib/use-replay.ts),
// with what the stage shows while the replay loads, when it can't load and when there is no replay; and the controls
// under it (play, time, speed, Jump to hand-off). The player's frame and cursor take the theme's tokens (index.css,
// "Replay player"); the cursor carries the name of who acts.
import type { ReactNode } from "react"
import { Pause, Play, SkipForward } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { ReplayMissing } from "@/data/types"
import { clock, withoutScheme } from "@/lib/format"
import { SPEEDS, type ReplayState } from "@/lib/use-replay"
import { WORDS } from "@/lib/words"
import { Hint } from "./bits"
import { Crumb } from "./crumb"
import { RetryButton } from "./page-state"

/** What the stage says when the replay is gone or cut short. */
const MISSING: Record<ReplayMissing, string> = { freed: WORDS.replayFreed, dropped: WORDS.replayDropped, none: WORDS.replayNone }
export const missingText = (missing: ReplayMissing | null) => MISSING[missing ?? "none"]

type StageProps = Pick<ReplayState, "status" | "missing" | "error" | "waiting" | "address" | "mount" | "retry">

/** What the stage shows instead of the replay: centred on the stage's own background. */
function StageNote({ children }: { children: ReactNode }) {
  return <div role="status" className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-muted p-4 text-center text-sm text-muted-foreground">{children}</div>
}

export function ReplayStage({ replay }: { replay: StageProps }) {
  return (
    <div className="flex flex-col" data-replay={replay.status}>
      <div className="flex items-center gap-2 border-b-2 border-line px-3 py-2">
        <span className="flex gap-1.5" aria-hidden>{[0, 1, 2].map((i) => <i key={i} className="size-2.5 rounded-full border-2 border-line bg-muted" />)}</span>
        <span data-address="" className="min-w-0 flex-1 truncate rounded-full border-2 border-border bg-muted px-3 text-sm text-muted-foreground">{withoutScheme(replay.address)}</span>
      </div>
      <div className="relative aspect-video overflow-hidden bg-muted">
        <div ref={replay.mount} className="cake-replay absolute inset-0" />
        {replay.status === "loading" && <StageNote><Crumb pose="look" className="w-16" label={WORDS.crumb.loading} />{WORDS.replayLoading}</StageNote>}
        {replay.status === "failed" && (
          <StageNote>
            <Crumb pose="oops" className="w-20" label={WORDS.crumb.error} />
            <span><b className="text-foreground">{WORDS.replayFailed}</b> {replay.error}</span>
            <RetryButton onClick={replay.retry} />
          </StageNote>
        )}
        {replay.status === "missing" && <StageNote><Crumb pose="sleep" className="w-20" label={WORDS.crumb.empty} />{missingText(replay.missing)}</StageNote>}
        {replay.waiting && <Badge variant="tag" className="absolute top-2 right-2">{WORDS.replayWaiting}</Badge>}
      </div>
    </div>
  )
}

/** Play / pause, where the replay is, its speed, and "Jump to hand-off" when the session has one. */
export function ReplayControls({ replay, durationMs }: { replay: ReplayState; durationMs: number }) {
  const ready = replay.status === "ready"
  const toggle = replay.playing ? "Pause" : "Play"
  return (
    <div className="flex flex-wrap items-center gap-2 border-t-2 border-line px-3 py-2">
      <Hint text={toggle}>
        <Button variant="outline" size="icon-sm" aria-label={toggle} disabled={!ready} onClick={replay.playing ? replay.pause : replay.play}>{replay.playing ? <Pause /> : <Play />}</Button>
      </Hint>
      <span data-clock="" className="font-mono text-sm">{`${clock(replay.timeMs)} / ${clock(durationMs)}`}</span>
      <ToggleGroup type="single" variant="outline" size="sm" value={String(replay.speed)} disabled={!ready} aria-label="Playback speed"
        onValueChange={(value) => value && replay.setSpeed(Number(value))}>
        {SPEEDS.map((speed) => <ToggleGroupItem key={speed} value={String(speed)}>{speed}×</ToggleGroupItem>)}
      </ToggleGroup>
      {replay.nextHandoff !== null && (
        <Button variant="ghost" size="sm" disabled={!ready} onClick={replay.jumpToHandoff}><SkipForward aria-hidden />{WORDS.jumpToHandoff}</Button>
      )}
    </div>
  )
}
