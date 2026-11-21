// The settings page's Time zone (DESIGN.md §6.5): one of hundreds of time zones, found by typing, as PostHog's project
// time zone is picked (frontend/src/scenes/settings/environment/TimezoneConfig.tsx: one searchable list of every zone,
// each with its UTC offset; MIT, no code copied). The first choice follows the computer or server AgentCake runs on,
// the default. The trigger is the dropdown pill; the list opens in a Popover under a search box: typing narrows it,
// the arrow keys move through it, Enter picks, Escape closes (the ARIA combobox pattern, the box holding the focus).
import { useEffect, useId, useMemo, useState, type KeyboardEvent } from "react"
import { ChevronDownIcon } from "lucide-react"
import { cn } from "cn"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { selectTriggerClass } from "@/components/ui/select"
import { WORDS } from "@/lib/words"

/** One choice: its value (an IANA name; "" follows this computer's time zone) and what the list shows. */
export type ZoneChoice = { name: string; label: string }

/** zones: /api/timezones' list; value: the setting; follow: what the first choice, "", says. */
export function TimezonePicker({ id, zones, value, follow, onPick }: {
  id?: string; zones: ZoneChoice[]; value: string; follow: string; onPick: (name: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [active, setActive] = useState(0)
  const list = useId()
  const choices = useMemo(() => [{ name: "", label: follow }, ...zones], [zones, follow])
  const words = search.trim().toLowerCase()
  const shown = words ? choices.filter((c) => c.label.toLowerCase().includes(words) || c.name.toLowerCase().includes(words)) : choices
  const optionId = (i: number) => `${list}-${i}`
  const show = (opened: boolean) => {
    setOpen(opened)
    setSearch("")
    setActive(Math.max(0, choices.findIndex((c) => c.name === value)))
  }
  const pick = (name: string) => {
    show(false)
    if (name !== value) onPick(name)
  }
  const move = (to: number) => setActive(Math.min(Math.max(to, 0), shown.length - 1))
  const keys = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") move(active + 1)
    else if (e.key === "ArrowUp") move(active - 1)
    else if (e.key === "Enter" && shown[active]) pick(shown[active].name)
    else return
    e.preventDefault()
  }
  // the choice the arrows reach (and, on opening, the one set) stays in view
  useEffect(() => { if (open) document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" }) })
  return (
    <Popover open={open} onOpenChange={show}>
      <PopoverTrigger id={id} className={cn(selectTriggerClass, "w-full")}>
        <span className="truncate">{choices.find((c) => c.name === value)?.label ?? value}</span>
        <ChevronDownIcon aria-hidden className="text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-72 p-0">
        <Input value={search} onChange={(e) => { setSearch(e.target.value); setActive(0) }} onKeyDown={keys}
          placeholder={WORDS.searchTimeZones} aria-label={WORDS.searchTimeZones} role="combobox" aria-expanded
          aria-controls={list} aria-activedescendant={shown[active] ? optionId(active) : undefined}
          className="rounded-b-none border-0 border-b-2 border-border focus-visible:ring-0 minimal:border-b" />
        <div id={list} role="listbox" aria-label={WORDS.timeZone} className="max-h-72 overflow-y-auto p-1">
          {shown.map((c, i) => (
            <div key={c.name || "follow"} id={optionId(i)} role="option" aria-selected={c.name === value}
              data-active={i === active || undefined} onPointerMove={() => setActive(i)} onClick={() => pick(c.name)}
              className="cursor-default rounded-md px-1.5 py-1 text-sm aria-selected:font-bold data-active:bg-accent data-active:text-accent-foreground">
              {c.label}
            </div>
          ))}
          {shown.length === 0 && <p className="px-1.5 py-1 text-sm text-muted-foreground">{WORDS.noTimeZoneMatches}</p>}
        </div>
      </PopoverContent>
    </Popover>
  )
}
