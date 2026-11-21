// Settings, like PostHog 1.0's setup page, in rows of two cards: your website's domain (the project: the top bar shows
// it) and the line to add to its pages, beside the page script's two settings; where visits come from and when each
// last arrived (asked again every refresh_ms), with what the server middleware says about your site's server, beside how
// AgentCake decides (the four layers and the lists' age, which are not settings, and the monthly update of the lists,
// which is: lists_auto_update, with its last run and a warning once updates fail in a row); keeping data (as cake 0.3.4: keep
// everything by default, a budget whose cleanup deletes the oldest replays of every kind of session, and the disk's
// floor), beside the registration and deleting everything. Data: GET /api/settings and GET /api/register; each change is saved at once with POST /api/settings,
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
import { BudgetWarning, Columns, CopyBlock, DocumentLink, PageHeader, SettingRow, Status, StorageUse } from "@/components/cake/bits"
import { Loaded } from "@/components/cake/page-state"
import { LAYERS } from "@/components/cake/reasons"
import { TimezonePicker, type ZoneChoice } from "@/components/cake/timezone-picker"
import { api, asApiError, useApi } from "@/data/api"
import type { Connection, LayerId, Registration, Settings, SettingsUpdate } from "@/data/types"
import { NO_VALUE, PERCENT, bytes, integer, mbToBytes, percent } from "@/lib/format"
import { PRODUCT_NAME } from "@/lib/product"
import { sessionCount } from "@/lib/counts"
import { WORDS } from "@/lib/words"
import { useSetProjectDomain } from "@/pages/project"

const CONNECTION: Record<Connection, { tone: "ok" | "warn" | "off"; label: string }> = {
  receiving: { tone: "ok", label: "Receiving" },
  waiting: { tone: "warn", label: "Waiting" },
  not_connected: { tone: "off", label: "Not connected" },
}
/** Where each layer works: on this computer and on a server, or only on a server (the same words on any install). */
const LAYER_WHERE: Record<LayerId, string> = {
  name: WORDS.layerLocalOrServer, verify: WORDS.layerServerOnly, environment: WORDS.layerLocalOrServer, behavior: WORDS.layerLocalOrServer,
}
const LAYER_WORDS: Record<LayerId, string> = {
  name: "This layer identifies agents by name in the User-Agent header and in signatures, using the built-in lists.",
  verify: `This layer verifies signatures and published IP ranges when ${PRODUCT_NAME} runs on a server.`,
  environment: "This layer checks for signs of automation, such as webdriver, a headless browser, or a cloud machine. It also runs the BotD and botscent rules.",
  behavior: "This layer analyzes mouse movements, keystrokes, and scrolling with the built-in model.",
}

export function SettingsPage() {
  const data = useApi((signal) => Promise.all([api.settings(signal), api.registration(signal), api.timezones(signal)]), [])
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Settings" lead={`All settings and data are stored on the server or computer where ${PRODUCT_NAME} runs.`} />
      <Loaded state={data} what="settings">{([s, r, t]) => <SettingsForm initial={s} registration={r} zones={t.zones} />}</Loaded>
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

function SettingsForm({ initial, registration, zones }: { initial: Settings; registration: Registration; zones: ZoneChoice[] }) {
  const [s, setS] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [domain, setDomain] = useState(initial.site_domain)
  const setProjectDomain = useSetProjectDomain()
  const [hidden, setHidden] = useState(initial.hide_selectors)
  const save = (update: SettingsUpdate) =>
    api.saveSettings(update).then((saved) => { setS(saved); setError(null); return saved }, (e: unknown) => { setError(asApiError(e).message); return null })
  // while the page is open, where visits come from is asked again; the rest of the form stays as it is.
  useEffect(() => {
    const timer = setInterval(() => {
      api.settings().then((now) => setS((was) => ({ ...was, sources: now.sources, last_seen: now.last_seen, server_half: now.server_half })), () => undefined)
    }, initial.refresh_ms)
    return () => clearInterval(timer)
  }, [initial.refresh_ms])
  const budget = mbToBytes(s.budget_mb), used = s.storage.used_bytes, warn = s.storage.warn_at_pct
  const where = s.route === "server" ? "this server" : "this computer"
  const lastSeen = (when: string | null) => <span className="text-xs text-muted-foreground">{when ? `Last received: ${when}` : "No data yet"}</span>
  const status = (source: keyof Settings["sources"]) => (
    <div className="flex flex-col items-end gap-1"><Status tone={CONNECTION[s.sources[source]].tone}>{CONNECTION[s.sources[source]].label}</Status>{lastSeen(s.last_seen[source])}</div>
  )
  const selectorsOk = readable(hidden)
  const places = s.lists.city_database, updated = s.lists.last_update
  const command = <code key="command" className="font-mono wrap-anywhere">{s.lists.update_command}</code>
  return (
    <>
      {error && <Alert variant="destructive"><AlertDescription>{`Your change couldn't be saved. ${error}`}</AlertDescription></Alert>}
      <Columns ratio="1-1" equalHeight>
        <Card>
          <CardHeader><CardTitle icon={Globe}>Your website</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Label htmlFor="site-domain">Your website's domain</Label>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save({ site_domain: domain }).then((saved) => { if (saved) { setDomain(saved.site_domain); setProjectDomain(saved.site_domain) } }) }}>
              <Input id="site-domain" value={domain} placeholder="shop.example.com" onChange={(e) => setDomain(e.target.value)} aria-describedby="site-domain-about" />
              <Button type="submit" variant="outline" disabled={domain === s.site_domain}>Save</Button>
            </form>
            <p id="site-domain-about" className="text-xs text-muted-foreground">Visits from other domains are stored but not included in dashboard metrics.</p>
            <SettingRow title="Site key" desc="The public site key is included in each page's source code and sent with every visit." control={<code className="font-mono text-sm">{s.site_key ?? NO_VALUE}</code>} />
            <p className="text-sm">{WORDS.scriptWhere}</p>
            <CopyBlock text={s.script_tag} />
            <Label htmlFor="time-zone">{WORDS.timeZone}</Label>
            <TimezonePicker id="time-zone" zones={zones} value={s.timezone} onPick={(name) => void save({ timezone: name })}
              follow={WORDS.followMachine(s.route === "server" ? "This server" : "This computer", s.timezone_machine.name, s.timezone_machine.short)} />
            <p className="text-xs text-muted-foreground">{WORDS.timeZoneAbout}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle icon={Code}>Page script</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <SettingRow title="Extra automation detection" tags={<Badge variant="tag">Off by default</Badge>}
              desc="Detects some automation tools and browser extensions by monitoring how they find elements on your page. This modifies functions that your page calls."
              control={<Switch checked={s.hook_dom} onCheckedChange={(on) => void save({ hook_dom: on })} aria-label="Extra automation detection" />} />
            <Label htmlFor="hide">Mask elements</Label>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (selectorsOk) void save({ hide_selectors: hidden.trim() }).then((saved) => saved && setHidden(saved.hide_selectors)) }}>
              <Input id="hide" value={hidden} placeholder=".account-email, #address" onChange={(e) => setHidden(e.target.value)} aria-invalid={!selectorsOk || undefined} aria-describedby="hide-about" />
              <Button type="submit" variant="outline" disabled={!selectorsOk || hidden.trim() === s.hide_selectors}>Save</Button>
            </form>
            <p id="hide-about" className={selectorsOk ? "text-xs text-muted-foreground" : "text-xs text-destructive"}>
              {selectorsOk
                ? <>Elements that match these CSS selectors are masked in replays and appear as empty boxes. Text typed into these elements isn't saved. Input text is always masked.<span className="mt-1 block">{`Changes to masking take effect the next time a page loads the ${PRODUCT_NAME} script.`}</span></>
                : "Enter CSS selectors supported by this browser. Separate selectors with commas, for example .account-email, #address."}
            </p>
          </CardContent>
        </Card>
      </Columns>
      <Columns ratio="1-1" equalHeight>
        <Card>
          <CardHeader><CardTitle icon={Plug}>Data sources</CardTitle></CardHeader>
          <CardContent>
            <SettingRow title="Your website" tags={<Badge variant="tag">{s.route === "server" ? "On a server" : "On this computer"}</Badge>}
              desc={s.route === "server" ? "Visits reach this server through your website's domain." : "Visits from a website on this computer (localhost) are recorded here."} control={status("site")} />
            <SettingRow title="Server middleware" tags={<Badge variant="tag">Optional</Badge>} control={status("server_half")}
              desc={<>The server middleware adds signed tokens to your pages. You can also import access logs. Both sources show each request's headers, signature validity, and IP address owner.{s.server_half.logs && <span className="mt-1 block">{`Last log import: ${s.server_half.logs.last} (${s.server_half.logs.format})`}{[...s.server_half.logs.missing, ...s.server_half.logs.empty].length > 0 && <span className="block">{`This log doesn't include ${[...s.server_half.logs.missing, ...s.server_half.logs.empty].join(", ")}.`}</span>}</span>}</>} />
            {s.server_half.missing.length > 0 && (
              <Alert variant="warn"><Server aria-hidden /><AlertDescription>{`Your server didn't receive ${s.server_half.missing.join(", ")} on its latest page requests. A proxy, CDN, or load balancer in front of the server removes these headers before the server middleware can record them.`}</AlertDescription></Alert>
            )}
            {s.route === "this_computer" && <Alert variant="warn"><Server aria-hidden /><AlertDescription><>This computer can't receive data from public visits. To record them, install {PRODUCT_NAME} on a server your site can reach. For setup steps, see <DocumentLink path="SERVER.md" />.</></AlertDescription></Alert>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle icon={Fingerprint}>How detection works</CardTitle></CardHeader>
          <CardContent>
            {(Object.keys(LAYERS) as LayerId[]).map((id) => (
              <SettingRow key={id} title={`${LAYERS[id].n} · ${LAYERS[id].name}`} desc={LAYER_WORDS[id]} control={<Badge variant="tag">{LAYER_WHERE[id]}</Badge>} />
            ))}
            <SettingRow title="Agent and network lists" desc={WORDS.listsBuilt(s.lists.built, s.lists.age_days === 1 ? "1 day" : `${s.lists.age_days} days`)}
              control={<Badge variant="tag">{s.lists.stale ? "Out of date" : "Up to date"}</Badge>} />
            <SettingRow title={WORDS.autoUpdate.title} tags={<Badge variant="tag">On by default</Badge>}
              desc={<>{s.lists_auto_update ? WORDS.autoUpdate.on(places) : WORDS.autoUpdate.off(command, places)}{updated && (
                <span className="mt-1 block wrap-anywhere">{updated.ok ? WORDS.autoUpdate.lastOk(updated.when) : WORDS.autoUpdate.lastFailed(updated.when, updated.error ?? NO_VALUE)}{!updated.ok && s.lists_auto_update && !s.lists.failing && <span className="block">{WORDS.autoUpdate.retry(PRODUCT_NAME)}</span>}</span>
              )}</>}
              control={<Switch checked={s.lists_auto_update} onCheckedChange={(on) => void save({ lists_auto_update: on })} aria-label={WORDS.autoUpdate.title} />} />
            {(s.lists.failing || s.lists.stale) && (
              <div className="flex flex-col gap-2">
                <Alert variant="warn"><AlertDescription>{s.lists.failing ? WORDS.autoUpdate.failing(integer(s.lists.failures)) : `These lists are more than ${s.lists.max_age_days} days old. To get newer lists, run this command or upgrade ${PRODUCT_NAME}:`}</AlertDescription></Alert>
                <CopyBlock text={s.lists.update_command} />
              </div>
            )}
          </CardContent>
        </Card>
      </Columns>
      <Columns ratio="1-1" equalHeight>
        <Card>
          <CardHeader><CardTitle icon={HardDrive}>Data retention</CardTitle></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <ToggleGroup type="single" variant="outline" value={String(s.retention_days)} onValueChange={(v) => v && void save({ retention_days: Number(v) })} aria-label="Session retention" className="flex-wrap">
              {s.retention_choices.map((d) => <ToggleGroupItem key={d} value={String(d)}>{d === 0 ? "Keep everything" : `${d} days`}</ToggleGroupItem>)}
            </ToggleGroup>
            {s.retention_days === 0
              ? <p className="text-sm text-muted-foreground">Sessions are kept until you delete them.</p>
              : <Alert variant="warn"><AlertDescription>Sessions older than {s.retention_days} days are deleted every night, including Agent sessions.</AlertDescription></Alert>}
            <StorageUse usedBytes={used} budgetBytes={budget} warnAtPct={warn} daysLeft={s.storage.days_left}
              disk={s.storage.disk} replaysStopped={s.storage.replays_stopped} />
            <BudgetWarning usedPct={percent(used, budget)} warnAtPct={warn} freeAtPct={s.storage.free_to_pct} autoFree={s.auto_free} full={s.storage.replays_stopped === "budget"} />
            <p className="text-xs text-faint-foreground">{`A warning appears here and on the dashboard when usage reaches ${warn}% (${bytes((budget * warn) / 100)}).`}</p>
            <SettingRow title="Disk budget" desc={`The maximum disk space the database can use on ${where}.`}
              control={<Select value={String(s.budget_mb)} onValueChange={(v) => void save({ budget_mb: Number(v) })}><SelectTrigger aria-label="Disk budget"><SelectValue /></SelectTrigger><SelectContent>{s.budget_choices_mb.map((mb) => <SelectItem key={mb} value={String(mb)}>{bytes(mbToBytes(mb))}</SelectItem>)}</SelectContent></Select>} />
            <SettingRow title="Automatic cleanup" tags={<Badge variant="tag">On by default</Badge>}
              desc={s.auto_free
                ? `When less than ${PERCENT - s.storage.free_to_pct}% of the budget is left, ${PRODUCT_NAME} deletes the oldest replays from all session types.`
                : "When the budget is full or the disk runs low, new replays aren't stored. Visits and classifications are still recorded, and dropped replay events are counted for each session."}
              control={<Switch checked={s.auto_free} onCheckedChange={(on) => void save({ auto_free: on })} aria-label="Automatic cleanup" />} />
          </CardContent>
        </Card>
        <div className="flex flex-col gap-5">
          <RegistrationCard registration={registration} />
          <Card className="flex-1">
            <CardHeader><CardTitle icon={Database}>Your data</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">{`${s.database.path} · ${bytes(used)} · ${sessionCount(s.database.sessions)}`}</p>
              <DeleteEverything sessions={s.database.sessions} where={where} onDeleted={() => api.settings().then(setS, () => undefined)} />
            </CardContent>
          </Card>
        </div>
      </Columns>
    </>
  )
}

/** No telemetry; what the registration sent, and how to have it deleted (PRIVACY.md). */
function RegistrationCard({ registration: r }: { registration: Registration }) {
  return (
    <Card>
      <CardHeader><CardTitle icon={ShieldCheck}>Data collection and registration</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="font-extrabold minimal:font-semibold">{PRODUCT_NAME} doesn't collect usage data or telemetry.</p>
        {r.sent ? (
          <>
            <p>{`Information sent to Tartini AI when you registered (${r.sent.when}):`}</p>
            <Card variant="sunk" size="sm" aria-label="Information sent to Tartini AI"><CardContent><pre className="font-mono text-xs break-words whitespace-pre-wrap">{r.sent.body}</pre></CardContent></Card>
            <p className="text-muted-foreground">{`To stop receiving product updates, use the unsubscribe link in any update email. To delete your registration, email ${r.delete_contact}.`}</p>
          </>
        ) : <p className="text-muted-foreground">{`This installation isn't registered. The registration form appears again the next time you open ${PRODUCT_NAME}.`}</p>}
      </CardContent>
    </Card>
  )
}

/** "Delete all data": a Dialog first, then every session and its replay goes (POST /api/delete). */
function DeleteEverything({ sessions, where, onDeleted }: { sessions: number; where: string; onDeleted: () => void }) {
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
          <DialogDescription>{`This deletes every session and its replay from ${where}, including the ${sessionCount(sessions)} in your session lists. You can't undo this action.`}</DialogDescription>
        </DialogHeader>
        {failed && <Alert variant="destructive"><AlertDescription>{`Not all data could be deleted. ${failed}`}</AlertDescription></Alert>}
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button variant="destructive" onClick={remove} disabled={busy}>Delete</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
