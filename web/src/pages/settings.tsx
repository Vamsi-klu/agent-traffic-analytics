// Settings (S5.5). Like PostHog 1.0's setup page: your website's domain (the project, D40: the top bar shows it) and the
// line to add to its pages; then where visits come from and when each last arrived (asked again every refresh_ms, so a first visit shows within I3), what
// the server half says about your site's server, retention and the disk (as cake 0.3.4: keep everything by default, a
// budget, free space from old human-only replays, K2 below the disk's floor), the page script's two settings, how
// AgentCake decides (the four layers and the lists' age, which are not settings), the registration (D32) and deleting
// everything. Data: GET /api/settings and GET /api/register; each change is saved at once with POST /api/settings,
// which answers the new state; "Delete all data" posts /api/delete after its Dialog.
import { useEffect, useState } from "react"
import { Code, Database, Fingerprint, Globe, HardDrive, Plug, Server, ShieldCheck, Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { BudgetWarning, Columns, CopyBlock, PageHeader, SettingRow, Status, StorageUse } from "@/components/cake/bits"
import { Loaded } from "@/components/cake/page-state"
import { LAYERS } from "@/components/cake/reasons"
import { api, asApiError, useApi } from "@/data/api"
import type { Connection, LayerId, Registration, Settings, SettingsUpdate } from "@/data/types"
import { bytes, mbToBytes, percent } from "@/lib/format"
import { PRODUCT_NAME } from "@/lib/product"
import { useSetProjectDomain } from "@/pages/project"

const CONNECTION: Record<Connection, { tone: "ok" | "warn" | "off"; label: string }> = {
  receiving: { tone: "ok", label: "Receiving" },
  waiting: { tone: "warn", label: "Waiting" },
  not_connected: { tone: "off", label: "Not connected" },
}
const LAYER_WORDS: Record<LayerId, string> = {
  name: "Uses the built-in lists to look for agent names in the User-Agent header and in signatures.",
  verify: `When ${PRODUCT_NAME} runs on a server, it checks signatures and published IP ranges.`,
  environment: "Checks for signs of automation: webdriver, a browser without a window, and cloud machines. Also runs the BotD and botscent rules.",
  behavior: "Uses the built-in model to judge mouse movements, keystrokes, and scrolling.",
}

export function SettingsPage() {
  const data = useApi((signal) => Promise.all([api.settings(signal), api.registration(signal)]), [])
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Settings" lead="Everything here is stored on this computer." />
      <Loaded state={data} what="settings">{([s, r]) => <SettingsForm initial={s} registration={r} />}</Loaded>
    </div>
  )
}

/** A CSS selector list this browser can read (an empty list is fine): what cake.js will be able to use. */
function readable(selectors: string) {
  try {
    document.createDocumentFragment().querySelector(selectors || "*")
    return true
  } catch {
    return false
  }
}

function SettingsForm({ initial, registration }: { initial: Settings; registration: Registration }) {
  const [s, setS] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [domain, setDomain] = useState(initial.site_domain)
  const setProjectDomain = useSetProjectDomain()
  const [hidden, setHidden] = useState(initial.hide_selectors)
  const save = (update: SettingsUpdate) =>
    api.saveSettings(update).then((saved) => { setS(saved); setError(null); return saved }, (e: unknown) => { setError(asApiError(e).message); return null })
  // I3: while the page is open, where visits come from is asked again; the rest of the form stays as it is.
  useEffect(() => {
    const timer = setInterval(() => {
      api.settings().then((now) => setS((was) => ({ ...was, sources: now.sources, last_seen: now.last_seen, server_half: now.server_half })), () => undefined)
    }, initial.refresh_ms)
    return () => clearInterval(timer)
  }, [initial.refresh_ms])
  const budget = mbToBytes(s.budget_mb), used = s.storage.used_bytes, warn = s.storage.warn_at_pct
  const lastSeen = (when: string | null) => <span className="text-xs text-muted-foreground">{when ? `Last: ${when}` : "Nothing yet"}</span>
  const status = (source: keyof Settings["sources"]) => (
    <div className="flex flex-col items-end gap-1"><Status tone={CONNECTION[s.sources[source]].tone}>{CONNECTION[s.sources[source]].label}</Status>{lastSeen(s.last_seen[source])}</div>
  )
  const selectorsOk = readable(hidden)
  return (
    <>
      {error && <Alert variant="destructive"><AlertDescription>Couldn't save that change. {error} Try again.</AlertDescription></Alert>}
      <Columns ratio="1-1">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Globe className="size-5" aria-hidden />Your website</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Label htmlFor="site-domain">Your website's domain</Label>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save({ site_domain: domain }).then((saved) => { if (saved) { setDomain(saved.site_domain); setProjectDomain(saved.site_domain) } }) }}>
                <Input id="site-domain" value={domain} placeholder="shop.example.com" onChange={(e) => setDomain(e.target.value)} aria-describedby="site-domain-about" />
                <Button type="submit" variant="outline" disabled={domain === s.site_domain}>Save</Button>
              </form>
              <p id="site-domain-about" className="text-xs text-muted-foreground">{PRODUCT_NAME} still stores visits from other sites. The dashboard excludes them.</p>
              <SettingRow title="Site key" desc="Your pages send it with every visit. It's in each page's source, so it isn't a secret." control={<code className="font-mono text-sm">{s.site_key ?? "—"}</code>} />
              <p className="text-sm">Add this line to every page of your site:</p>
              <CopyBlock text={s.script_tag} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Plug className="size-5" aria-hidden />Where visits come from</CardTitle></CardHeader>
            <CardContent>
              <SettingRow title="Your website" tags={<Badge variant="tag">{s.route === "server" ? "On a server" : "On this computer"}</Badge>}
                desc={s.route === "server" ? "Visits from your site reach this server through your site's own domain." : "A site on this computer (localhost) sends its visits here."} control={status("site")} />
              <SettingRow title="Server half" tags={<Badge variant="tag">Optional</Badge>} control={status("server_half")}
                desc={<>Your site's server adds a small signed note to each page, or you import its log. The note or the log gives the request headers, the signature check, and the IP owner. This catches ChatGPT agent and the first page of Claude in Chrome.{s.server_half.logs && <span className="mt-1 block">{`A ${s.server_half.logs.format} log was imported ${s.server_half.logs.last}.`}{[...s.server_half.logs.missing, ...s.server_half.logs.empty].length > 0 && ` The log has no ${[...s.server_half.logs.missing, ...s.server_half.logs.empty].join(", ")}.`}</span>}</>} />
              {s.server_half.missing.length > 0 && (
                <Alert variant="warn"><Server aria-hidden /><AlertDescription className="text-foreground">{`${s.server_half.missing.join(", ")} didn't reach your site's server on its latest page requests. Something in front of the server, such as a proxy, a CDN, or a load balancer, removes them. As a result, the Server half says less about each visit.`}</AlertDescription></Alert>
              )}
              {s.route === "this_computer" && <Alert variant="warn"><Server aria-hidden /><AlertDescription className="text-foreground">Visitors to a public website can't reach this computer. To see them, install {PRODUCT_NAME} on a server your site can reach. See SERVER.md in the {PRODUCT_NAME} folder.</AlertDescription></Alert>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><HardDrive className="size-5" aria-hidden />Data retention</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ToggleGroup type="single" variant="outline" value={String(s.retention_days)} onValueChange={(v) => v && void save({ retention_days: Number(v) })} aria-label="Session retention" className="flex-wrap">
                {s.retention_choices.map((d) => <ToggleGroupItem key={d} value={String(d)}>{d === 0 ? "Keep everything" : `${d} days`}</ToggleGroupItem>)}
              </ToggleGroup>
              {s.retention_days === 0
                ? <p className="text-sm text-muted-foreground">Every session stays until you delete it.</p>
                : <Alert variant="warn"><AlertDescription className="text-foreground">Sessions older than {s.retention_days} days are deleted every night, including sessions with an agent.</AlertDescription></Alert>}
              <StorageUse usedBytes={used} budgetBytes={budget} warnAtPct={warn} daysLeft={s.storage.days_left}
                disk={s.storage.disk} replaysStopped={s.storage.replays_stopped} />
              <BudgetWarning usedPct={percent(used, budget)} warnAtPct={warn} autoFree={s.auto_free} full={s.storage.replays_stopped === "budget"} />
              <p className="text-xs text-faint-foreground">{`A warning appears on this page and on the dashboard at ${warn}%, which is ${bytes((budget * warn) / 100)}.`}</p>
              <SettingRow title="Disk budget" desc="The most disk space the database can use on this computer"
                control={<Select value={String(s.budget_mb)} onValueChange={(v) => void save({ budget_mb: Number(v) })}><SelectTrigger aria-label="Disk budget"><SelectValue /></SelectTrigger><SelectContent>{s.budget_choices_mb.map((mb) => <SelectItem key={mb} value={String(mb)}>{bytes(mbToBytes(mb))}</SelectItem>)}</SelectContent></Select>} />
              <SettingRow title="Cleanup when the budget is full" tags={<Badge variant="tag">On by default</Badge>}
                desc={s.auto_free
                  ? `Deletes replays until use is down to ${s.storage.free_to_pct}% of the budget. It deletes only Human sessions with no activity in the last hour, oldest first; Agent and Unknown sessions keep their replays. If the disk itself runs low, it deletes the oldest replays of any session instead, Human ones first, so new replays are still stored. If other files fill the disk, it deletes nothing and new replays wait for room. Visits and verdicts always stay.`
                  : "When the budget is full or the disk runs low, new replays aren't stored. Visits and verdicts are still recorded, and each session notes how many events were dropped."}
                control={<Switch checked={s.auto_free} onCheckedChange={(on) => void save({ auto_free: on })} aria-label="Free space automatically" />} />
            </CardContent>
          </Card>
        </div>
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Code className="size-5" aria-hidden />Page script</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <SettingRow title="Page lookup monitoring" tags={<Badge variant="tag">Off by default</Badge>}
                desc="The page script wraps your site's document lookups, such as querySelector and getElementById, to notice when an automation tool calls them. This catches some extensions. Wrapping changes functions your pages run, so it's off unless you turn it on."
                control={<Switch checked={s.hook_dom} onCheckedChange={(on) => void save({ hook_dom: on })} aria-label="Page lookup monitoring" />} />
              <Label htmlFor="hide">CSS masking selectors</Label>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (selectorsOk) void save({ hide_selectors: hidden.trim() }).then((saved) => saved && setHidden(saved.hide_selectors)) }}>
                <Input id="hide" value={hidden} placeholder=".account-email, #address" onChange={(e) => setHidden(e.target.value)} aria-invalid={!selectorsOk || undefined} aria-describedby="hide-about" />
                <Button type="submit" variant="outline" disabled={!selectorsOk || hidden.trim() === s.hide_selectors}>Save</Button>
              </form>
              <p id="hide-about" className={selectorsOk ? "text-xs text-muted-foreground" : "text-xs text-destructive"}>
                {selectorsOk ? "Replays show these parts as empty boxes, like data-cake-private, and keep nothing typed into them. Every input is masked anyway. Pages use the new list the next time they load the page script." : "This browser can't read the entries as CSS selectors. Separate selectors with commas, like .account-email, #address."}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Fingerprint className="size-5" aria-hidden />How detection works</CardTitle></CardHeader>
            <CardContent>
              {(Object.keys(LAYERS) as LayerId[]).map((id) => (
                <SettingRow key={id} title={`${LAYERS[id].n} · ${LAYERS[id].name}`} desc={LAYER_WORDS[id]} control={<Badge variant="tag">{s.layers[id] ? "Runs locally" : "Server only"}</Badge>} />
              ))}
              <SettingRow title="Agent and network lists" desc={`The lists were built ${s.lists.built}, ${s.lists.age_days === 1 ? "1 day" : `${s.lists.age_days} days`} ago. They come with each release of ${PRODUCT_NAME}.`}
                control={<Badge variant="tag">{s.lists.stale ? "Out of date" : "Up to date"}</Badge>} />
              {s.lists.stale && (
                <div className="flex flex-col gap-2">
                  <Alert variant="warn"><AlertDescription className="text-foreground">{`These lists are more than ${s.lists.max_age_days} days old. Download newer ones with this command, or upgrade ${PRODUCT_NAME}:`}</AlertDescription></Alert>
                  <CopyBlock text={s.lists.update_command} />
                </div>
              )}
            </CardContent>
          </Card>
          <RegistrationCard registration={registration} />
          <Card variant="flat">
            <CardHeader><CardTitle className="flex items-center gap-2"><Database className="size-5" aria-hidden />Your data</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">{`${s.database.path} · ${bytes(used)} · ${s.database.sessions} sessions`}</p>
              <DeleteEverything sessions={s.database.sessions} onDeleted={() => api.settings().then(setS, () => undefined)} />
            </CardContent>
          </Card>
        </div>
      </Columns>
    </>
  )
}

/** No telemetry; what the registration sent, and how to have it deleted (D32, PRIVACY.md). */
function RegistrationCard({ registration: r }: { registration: Registration }) {
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5" aria-hidden />Data collection and registration</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="font-extrabold">{PRODUCT_NAME} doesn't collect usage data or telemetry.</p>
        {r.sent ? (
          <>
            <p>{`You registered ${r.sent.when}. This is what was sent to Tartini AI:`}</p>
            <Card variant="sunk" size="sm" aria-label="What was sent"><CardContent><pre className="font-mono text-xs break-words whitespace-pre-wrap">{r.sent.body}</pre></CardContent></Card>
            <p className="text-muted-foreground">{`To stop product updates, use the unsubscribe link in any update email. To have your registration deleted, write to ${r.delete_contact}.`}</p>
          </>
        ) : <p className="text-muted-foreground">{`You haven't registered. ${PRODUCT_NAME} asks again the next time you open it.`}</p>}
      </CardContent>
    </Card>
  )
}

/** "Delete all data": a Dialog first, then every session and its replay goes (POST /api/delete). */
function DeleteEverything({ sessions, onDeleted }: { sessions: number; onDeleted: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const remove = () => {
    setBusy(true)
    api.deleteEverything().then(() => { setOpen(false); setFailed(null); onDeleted() }, (e: unknown) => setFailed(asApiError(e).message)).finally(() => setBusy(false))
  }
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); setFailed(null) }}>
      <DialogTrigger asChild><Button variant="destructive" size="sm" className="self-start"><Trash2 aria-hidden />Delete all data</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete all sessions</DialogTitle>
          <DialogDescription>{`This deletes every session and its replay from this computer, including ${sessions} sessions in the lists and any sessions the lists leave out. You can't undo this.`}</DialogDescription>
        </DialogHeader>
        {failed && <Alert variant="destructive"><AlertDescription>{`Couldn't delete everything. ${failed} Try again.`}</AlertDescription></Alert>}
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button variant="destructive" onClick={remove} disabled={busy}>Delete</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
