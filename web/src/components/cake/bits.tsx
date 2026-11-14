// Small cake building blocks made only of shadcn components + theme classes. DESIGN.md §6
import { useState, type ReactNode } from "react"
import { Check, Copy, HardDrive } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import type { Disk, ReplaysStopped } from "@/data/types"
import { aboutDays, bytes, percent } from "@/lib/format"
import { PRODUCT_NAME } from "@/lib/product"
import { cn } from "@/lib/utils"

/** Terminal-style block with a Copy button: commands and the one sentence for a coding agent. */
export function CopyBlock({ text, className }: { text: string; className?: string }) {
  const [done, setDone] = useState(false)
  return (
    <div className={cn("flex items-stretch overflow-hidden rounded-xl border-2 border-line bg-foreground", className)}>
      <pre className="min-w-0 flex-1 p-3 font-mono text-sm break-words whitespace-pre-wrap text-background">{text}</pre>
      <div className="flex items-center border-l-2 border-line bg-card px-2">
        <Button variant="ghost" size="sm" onClick={() => { void navigator.clipboard?.writeText(text); setDone(true) }}>
          {done ? <Check aria-hidden /> : <Copy aria-hidden />}{done ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  )
}

/** Page title + one sentence + optional actions on the right. */
export function PageHeader({ title, lead, actions }: { title: string; lead: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-col gap-1"><h1 className="text-3xl font-semibold">{title}</h1><p className="text-muted-foreground">{lead}</p></div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/** Section title row. */
export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mt-8 mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-xl font-semibold">{children}</h2>
      {aside && <div className="text-sm">{aside}</div>}
    </div>
  )
}

/** A plain number tile (not highlighted). help = a small "?" with a tooltip after the label (Bots: BotHelp). */
export function StatCard({ label, value, sub, mark, muted = false, help }: { label: string; value: string; sub: string; mark: ReactNode; muted?: boolean; help?: ReactNode }) {
  return (
    <Card variant="flat" size="sm" className={cn(muted && "opacity-70")}>
      <CardContent className="flex flex-col gap-1">
        <span className="flex items-center gap-2 text-sm font-bold text-muted-foreground">{mark}{label}{help}</span>
        <span className="font-heading text-3xl leading-none font-semibold">{value}</span>
        <span className="text-xs text-muted-foreground">{sub}</span>
      </CardContent>
    </Card>
  )
}

/** Disk use against the budget, with the warning line (warnAtPct: from the settings, 80 by default). */
export function StorageMeter({ usedPct, warnAtPct }: { usedPct: number; warnAtPct: number }) {
  return (
    <div className="relative">
      <Progress value={usedPct} tone={usedPct >= warnAtPct ? "warn" : "ok"} aria-label={`Disk used ${usedPct}%`} />
      <span aria-hidden title={`Warning at ${warnAtPct}%`} className="absolute -top-1.5 -bottom-1.5 border-l-2 border-dashed border-foreground" style={{ left: `${warnAtPct}%` }} />
    </div>
  )
}

/** Why new replays aren't stored while the disk is below its floor: its free space, how far below the floor
 *  that is (the two can round to the same size) and the floor. A full budget has the page's own warning. */
const DISK_STOPPED: Partial<Record<NonNullable<ReplaysStopped>, (free: string, short: string, floor: string) => string>> = {
  disk_full_other: (free, short, floor) => `Other files are filling this disk. Only ${free} is free, ${short} less than the ${floor} ${PRODUCT_NAME} keeps free. Deleting every old replay wouldn't free enough space, so ${PRODUCT_NAME} deleted none. New replays start being stored again on their own once there's room. Visits and verdicts are still recorded.`,
  disk: (free, short, floor) => `Only ${free} is free on this disk. That's ${short} less than the ${floor} ${PRODUCT_NAME} keeps free, so new replays aren't stored. Free up space, or turn on cleanup in Settings to delete the oldest replays. Visits and verdicts are still recorded.`,
}

/** Disk use in a bar and a line: what is used of the budget, and when it is full at last week's pace (daysLeft: null when
 *  nothing was added last week); while new replays stop because the disk is below its floor, an Alert warn says why
 *  (disk, replaysStopped: the API's storage). The settings page and the dashboard's Disk section. */
export function StorageUse({ usedBytes, budgetBytes, warnAtPct, daysLeft, disk, replaysStopped }: {
  usedBytes: number; budgetBytes: number; warnAtPct: number; daysLeft: number | null; disk: Disk; replaysStopped: ReplaysStopped
}) {
  const usedPct = percent(usedBytes, budgetBytes), diskStopped = replaysStopped && DISK_STOPPED[replaysStopped]
  return (
    <>
      <StorageMeter usedPct={usedPct} warnAtPct={warnAtPct} />
      <div className="flex flex-wrap justify-between gap-2 text-sm"><span><b>{bytes(usedBytes)}</b>{` of ${bytes(budgetBytes)} used, ${usedPct}%`}</span><span className="text-muted-foreground">{daysLeft === null ? "Nothing was added in the last week." : `At last week's pace, the budget fills up in ${aboutDays(daysLeft)}.`}</span></div>
      {diskStopped && <Alert variant="warn"><HardDrive aria-hidden /><AlertDescription className="text-foreground">{diskStopped(bytes(disk.free), bytes(disk.min_free - disk.free), bytes(disk.min_free))}</AlertDescription></Alert>}
    </>
  )
}

/** The disk budget's warning (DESIGN.md §1.1, like 0.3.4's), on the dashboard and the settings page: from warnAtPct on,
 *  how full it is and what happens when it is full; once it is full and nothing more can be freed (the API's
 *  replays_stopped "budget"), that new replays aren't stored now and what to do. Nothing below warnAtPct. */
export function BudgetWarning({ usedPct, warnAtPct, autoFree, full }: { usedPct: number; warnAtPct: number; autoFree: boolean; full: boolean }) {
  if (!full && usedPct < warnAtPct) return null
  const whenFull = autoFree
    ? `${PRODUCT_NAME} deletes the oldest replays of Human sessions to make room. Agent and Unknown sessions keep their replays. Visits and verdicts always stay.`
    : `${PRODUCT_NAME} stops storing new replays. Visits and verdicts are still recorded. To keep storing replays, turn on cleanup in Settings.`
  const nowFull = autoFree
    ? "The disk budget is full and nothing more can be freed: the replays left belong to Agent sessions, Unknown sessions, and sessions active in the last hour. New replays aren't stored until there's room. To keep them, raise the budget. Visits and verdicts are still recorded."
    : "The disk budget is full, so new replays aren't stored. Visits and verdicts are still recorded. Raise the budget, or turn on cleanup in Settings."
  return <Alert variant="warn"><HardDrive aria-hidden /><AlertDescription className="text-foreground">{full ? nowFull : `You've used ${usedPct}% of the disk budget. When it's full, ${whenFull}`}</AlertDescription></Alert>
}

/** System status with a dot: receiving / waiting / not connected. */
export function Status({ tone, children }: { tone: "ok" | "warn" | "off"; children: ReactNode }) {
  const dot = tone === "ok" ? "bg-ok" : tone === "warn" ? "bg-warn" : "bg-muted"
  return <span className="inline-flex items-center gap-2 text-sm font-extrabold whitespace-nowrap"><span aria-hidden className={cn("size-2.5 rounded-full border-2 border-line", dot)} />{children}</span>
}

/** One settings row: title (+ tags), one or two sentences, the control on the right. */
export function SettingRow({ title, tags, desc, control }: { title: string; tags?: ReactNode; desc: ReactNode; control: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-5 gap-y-2 border-b border-border py-4 last:border-b-0">
      <div className="flex flex-col gap-0.5">
        <h4 className="flex flex-wrap items-center gap-2 font-extrabold">{title}{tags}</h4>
        <div className="text-sm text-muted-foreground">{desc}</div>
      </div>
      <div>{control}</div>
    </div>
  )
}

/** Page columns. Pages never write their own grid ratios. 3-2 = main + side; 1-1 = two equal columns. Stacks below lg. */
export function Columns({ ratio, children, className }: { ratio: "3-2" | "1-1"; children: ReactNode; className?: string }) {
  return <div className={cn("grid items-start gap-5", ratio === "3-2" ? "lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" : "lg:grid-cols-2", className)}>{children}</div>
}
