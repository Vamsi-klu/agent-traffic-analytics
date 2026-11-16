// Small cake building blocks made only of shadcn components + theme classes. DESIGN.md §6
import { createContext, useContext, useState, type ReactElement, type ReactNode } from "react"
import { Check, Copy, HardDrive, Info, type LucideIcon } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Disk, ReplaysStopped } from "@/data/types"
import { PERCENT, aboutDays, bytes, percent } from "@/lib/format"
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
/** A page's title, with a lead under it and actions on the right. as="h2": the same title for each part of a page that
 *  has several (the dashboard's Key metrics, Deep dive and Reference, under the page's own h1). */
export function PageHeader({ title, lead, actions, as: Heading = "h1" }: { title: string; lead?: string; actions?: ReactNode; as?: "h1" | "h2" }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-col gap-1"><Heading className="text-3xl font-semibold">{title}</Heading>{lead && <p className="text-muted-foreground">{lead}</p>}</div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/** Section title row. */
/** A section's title, with a link or a note on the right (the session page's Server half and Every action). */
export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mt-8 mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-xl font-semibold">{children}</h2>
      {aside && <div className="text-sm">{aside}</div>}
    </div>
  )
}

/** What a chart or table card shows instead of its chart or rows when the range has nothing for it, as tall as a short
 *  chart. */
export function CardEmpty({ text }: { text: string }) {
  return <p className="flex h-40 items-center justify-center text-center text-sm text-muted-foreground">{text}</p>
}

/** What a hint says: one paragraph, or several, each on a line of its own. */
export type HintText = ReactNode | string[]

/** A hint's text as paragraphs: blocks, so the lines stack in the tooltip and a screen reader hears them apart. */
function HintLines({ text }: { text: HintText }) {
  return Array.isArray(text) ? text.map((line) => <p key={line}>{line}</p>) : <p>{text}</p>
}

/** Inside a link (a session row), the link has the focus and nothing inside it may take focus of its own: hints there
 *  open on hover only. */
const InsideLinkContext = createContext(false)

export function InsideLink({ children }: { children: ReactNode }) {
  return <InsideLinkContext.Provider value>{children}</InsideLinkContext.Provider>
}

/** The interface's one way to show text on hover (DESIGN.md §6, §11): the theme tooltip, never the browser's own title
 *  box, and it opens on keyboard focus too. children: the element it explains, which takes the tooltip's hover and focus
 *  handlers (so it passes its props on to its element). focusable: the element is no button or link (a badge, a name),
 *  so it takes focus of its own for the hint, except inside a link. */
export function Hint({ text, focusable = false, children }: { text: HintText; focusable?: boolean; children: ReactElement }) {
  const insideLink = useContext(InsideLinkContext)
  // never a tabIndex key otherwise: an undefined one would still replace a toggle item's own roving tab stop
  const focus = focusable && !insideLink ? { tabIndex: 0 } : {}
  return (
    <Tooltip>
      <TooltipTrigger asChild {...focus}>{children}</TooltipTrigger>
      <TooltipContent><HintLines text={text} /></TooltipContent>
    </Tooltip>
  )
}

/** An icon beside a name that says more about it on hover and on focus: InfoTip's information icon, BotHelp's "?".
 *  label: the icon's name for screen readers. The icon and its place in the line stay 14 px; an empty layer 9 px
 *  around it makes what takes the pointer 32 px square, as everything clickable is (DESIGN.md §10). */
export function IconTip({ icon: Icon, label, text }: { icon: LucideIcon; label: string; text: HintText }) {
  return (
    <Tooltip>
      <TooltipTrigger aria-label={label} className="relative inline-flex text-faint-foreground after:absolute after:-inset-2.25 hover:text-foreground"><Icon className="size-3.5" aria-hidden /></TooltipTrigger>
      <TooltipContent><HintLines text={text} /></TooltipContent>
    </Tooltip>
  )
}

/** What a metric or a chart means, behind an information icon beside its name: one line per paragraph. */
export function InfoTip({ label, lines }: { label: string; lines: string[] }) {
  return <IconTip icon={Info} label={`About ${label}`} text={lines} />
}

/** A number on a card: its name (with a help icon beside it), the number, and a line under it when there is something
 *  to say about this number (data, or why it is missing). */
export function StatCard({ label, value, sub, mark, muted = false, help }: { label: string; value: string; sub?: string; mark: ReactNode; muted?: boolean; help?: ReactNode }) {
  return (
    <Card variant="flat" size="sm" className={cn(muted && "opacity-70")}>
      <CardContent className="flex flex-col gap-1">
        <span className="flex items-center gap-2 text-sm font-bold text-muted-foreground">{mark}{label}{help}</span>
        <span className="font-heading text-3xl leading-none font-semibold">{value}</span>
        {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
      </CardContent>
    </Card>
  )
}

/** Disk use against the budget, with the warning line (warnAtPct: from the settings, 80 by default). */
export function StorageMeter({ usedPct, warnAtPct }: { usedPct: number; warnAtPct: number }) {
  return (
    <div className="relative">
      <Progress value={usedPct} tone={usedPct >= warnAtPct ? "warn" : "ok"} aria-label={`Budget used: ${usedPct}%`} />
      <Hint text={`Warning threshold: ${warnAtPct}%`}>
        <span aria-hidden data-warn-line="" className="absolute -top-1.5 -bottom-1.5 border-l-2 border-dashed border-foreground" style={{ left: `${warnAtPct}%` }} />
      </Hint>
    </div>
  )
}

/** Why new replays aren't stored while the disk is below its floor: its free space, how far below the floor that is
 *  (the two can round to the same size) and the floor. None is deleted for it; a full budget has its own warning. */
const DISK_STOPPED: Partial<Record<NonNullable<ReplaysStopped>, (free: string, short: string, floor: string) => string>> = {
  disk: (free, short, floor) => `New replays are paused until ${floor} of disk space is free, and then resume automatically. This disk has ${free} free and needs ${short} more. Visits and classifications are still recorded.`,
}

/** Disk use in a bar and a line: what is used of the budget, and when it is full at last week's pace (daysLeft: null when
 *  nothing was added last week), with DiskStoppedWarning under it (disk, replaysStopped: the API's storage). The
 *  settings page. */
export function StorageUse({ usedBytes, budgetBytes, warnAtPct, daysLeft, disk, replaysStopped }: {
  usedBytes: number; budgetBytes: number; warnAtPct: number; daysLeft: number | null; disk: Disk; replaysStopped: ReplaysStopped
}) {
  const usedPct = percent(usedBytes, budgetBytes)
  return (
    <>
      <StorageMeter usedPct={usedPct} warnAtPct={warnAtPct} />
      <div className="flex flex-wrap justify-between gap-2 text-sm"><span><b>{bytes(usedBytes)}</b>{` of ${bytes(budgetBytes)} used (${usedPct}%)`}</span><span className="text-muted-foreground">{daysLeft === null ? "No data was added last week." : `At last week's growth rate, stored data will reach the disk budget in ${aboutDays(daysLeft)}.`}</span></div>
      <DiskStoppedWarning disk={disk} replaysStopped={replaysStopped} />
    </>
  )
}

/** While new replays stop because the disk is below its floor, an Alert warn says why; nothing otherwise. Under the
 *  settings page's StorageUse, and on the dashboard beside BudgetWarning. */
export function DiskStoppedWarning({ disk, replaysStopped }: { disk: Disk; replaysStopped: ReplaysStopped }) {
  const diskStopped = replaysStopped && DISK_STOPPED[replaysStopped]
  if (!diskStopped) return null
  return <Alert variant="warn"><HardDrive aria-hidden /><AlertDescription className="text-foreground">{diskStopped(bytes(disk.free), bytes(disk.min_free - disk.free), bytes(disk.min_free))}</AlertDescription></Alert>
}

/** The disk budget's warning (DESIGN.md §1.1, like 0.3.4's), on the dashboard and the settings page: from warnAtPct on,
 *  how full it is and what happens next (with auto_free, from freeAtPct the oldest replays are deleted, of every kind of
 *  session; without, new replays stop when it is full); once it is full and nothing is left to delete (the API's
 *  replays_stopped "budget"), that new replays aren't stored now and what to do. Nothing below warnAtPct. */
export function BudgetWarning({ usedPct, warnAtPct, freeAtPct, autoFree, full }: {
  usedPct: number; warnAtPct: number; freeAtPct: number; autoFree: boolean; full: boolean
}) {
  if (!full && usedPct < warnAtPct) return null
  const next = autoFree
    ? `When less than ${PERCENT - freeAtPct}% is left, ${PRODUCT_NAME} deletes the oldest replays across all session types. Visits and classifications are always kept.`
    : "When the budget is full, new replays aren't stored unless Automatic cleanup is on in Settings. Visits and classifications are still recorded."
  const nowFull = autoFree
    ? "The disk budget is full. All remaining replays belong to active sessions and can't be deleted yet. Visits and classifications are still recorded, and new replays resume when cleanup or a larger budget makes room."
    : "The disk budget is full, so new replays aren't stored. Visits and classifications are still recorded. To store replays again, increase the budget or turn on Automatic cleanup in Settings."
  return <Alert variant="warn"><HardDrive aria-hidden /><AlertDescription className="text-foreground">{full ? nowFull : `Disk budget used: ${usedPct}%. ${next}`}</AlertDescription></Alert>
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
/** Page columns. equalHeight: one row of cards side by side, each as tall as the tallest (cards in a row always match);
 *  without it, columns that each stack their own cards. */
export function Columns({ ratio, equalHeight = false, children, className }: { ratio: "3-2" | "1-1"; equalHeight?: boolean; children: ReactNode; className?: string }) {
  return <div className={cn("grid gap-5", equalHeight ? "items-stretch" : "items-start", ratio === "3-2" ? "lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" : "lg:grid-cols-2", className)}>{children}</div>
}
