// Installed, no visits yet: how to connect the website, as PostHog 1.0's setup page asked "What URL will you
// be using PostHog on?" and gave the snippet, and its dashboard waited under "Start sending events" until the first:
// 1 the website's address (site_domain, the project the top bar shows); 2 where AgentCake runs: this computer for a
// site on it, a server for a public website (SERVER.md); 3 the page script, through a coding agent (`agentcake setup
// --print --site`), by hand or in a terminal, with the server half as an optional part; 4 the first visit, asked for
// again every refresh_ms and shown when it comes. The dashboard shows the same page until the first session. Data:
// /api/setup and /api/settings; POST /api/settings saves the address.
import { useEffect, useState } from "react"
import { Code, List, Monitor, Plug, Server } from "lucide-react"
import { Navigate, useNavigate } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { CopyBlock, Status } from "@/components/cake/bits"
import { OnboardingLayout, OnboardingStep, OrSeparator } from "@/components/cake/onboarding"
import { Loaded } from "@/components/cake/page-state"
import { SessionRow } from "@/components/cake/session-row"
import { api, asApiError, useApi } from "@/data/api"
import type { SessionSummary, Settings, Setup } from "@/data/types"
import { PRODUCT_NAME } from "@/lib/product"
import { WORDS } from "@/lib/words"
import { useSetProjectDomain } from "@/pages/project"

export function HomePage() {
  const navigate = useNavigate()
  const setup = useApi((signal) => api.setup(signal), [])
  return (
    <Loaded state={setup} what="the setup steps">
      {(s) => (s.recorded.sessions > 0 ? <Navigate to="/dashboard" replace /> : <Onboarding setup={s} onOpen={() => navigate("/dashboard")} />)}
    </Loaded>
  )
}

/** The four steps; onOpen: what "Open dashboard" does once the first visit has come. */
export function Onboarding({ setup, onOpen }: { setup: Setup; onOpen: () => void }) {
  const settings = useApi((signal) => api.settings(signal), [])
  return <Loaded state={settings} what="your website's settings">{(s) => <Steps setup={setup} initial={s} onOpen={onOpen} />}</Loaded>
}

function Steps({ setup, initial, onOpen }: { setup: Setup; initial: Settings; onOpen: () => void }) {
  const [saved, setSaved] = useState(initial.site_domain)
  const [domain, setDomain] = useState(initial.site_domain)
  const [error, setError] = useState<string | null>(null)
  const [lang, setLang] = useState<keyof Setup["sentence"]>("en")
  const [first, setFirst] = useState<SessionSummary | null>(null)
  const setProjectDomain = useSetProjectDomain()
  // Step 4: asked again until the first session is there (within refresh_ms of its arrival).
  useEffect(() => {
    if (first) return undefined
    const timer = setInterval(() => {
      api.sessions({}).then((page) => { if (page.results.length) setFirst(page.results[page.results.length - 1]) }, () => undefined)
    }, initial.refresh_ms)
    return () => clearInterval(timer)
  }, [first, initial.refresh_ms])
  const save = () => api.saveSettings({ site_domain: domain }).then(
    (answer) => { setSaved(answer.site_domain); setDomain(answer.site_domain); setProjectDomain(answer.site_domain); setError(null) },
    (e: unknown) => setError(asApiError(e).message))
  const onServer = initial.route === "server"
  return (
    <OnboardingLayout
      status={<Badge variant="tag"><Plug aria-hidden />{PRODUCT_NAME} is running {onServer ? "on this server" : "on this computer"}</Badge>}
      title="Connect your website"
      lead={WORDS.homeLead}
      note="Four steps. Sessions stay on the computer that runs this page."
      example={setup.example}
    >
      <OnboardingStep n={1} title="Your website's address">
        <Label htmlFor="site-domain">Your website's domain</Label>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <Input id="site-domain" value={domain} placeholder="shop.example.com" onChange={(e) => setDomain(e.target.value)} aria-describedby="site-domain-about" />
          <Button type="submit" variant="outline" disabled={domain === saved}>Save</Button>
        </form>
        {error && <Alert variant="destructive"><AlertDescription>Couldn't save the address. {error} Try again.</AlertDescription></Alert>}
        <p id="site-domain-about" className="text-xs text-muted-foreground">${PRODUCT_NAME} still stores visits from other sites. The dashboard excludes them.</p>
      </OnboardingStep>

      <OnboardingStep n={2} title={`Where ${PRODUCT_NAME} runs`}>
        {onServer ? (
          <p className="text-sm">{PRODUCT_NAME} runs on this server. Visits from your site reach it through your site's own domain.</p>
        ) : (
          <Tabs defaultValue="computer" className="gap-3">
            <TabsList className="max-w-full overflow-x-auto">
              <TabsTrigger value="computer"><Monitor aria-hidden />On this computer</TabsTrigger>
              <TabsTrigger value="server"><Server aria-hidden />On a server</TabsTrigger>
            </TabsList>
            <TabsContent value="computer"><p className="text-sm">A website you run on this computer, such as a development server on localhost, sends its visits here. There's nothing to set up.</p></TabsContent>
            <TabsContent value="server" className="flex flex-col gap-2">
              <p className="text-sm">Visitors to a public website can't reach this computer. Run {PRODUCT_NAME} on a server your site can reach, open its page through a tunnel, and connect your site there.</p>
              <CopyBlock text={setup.server} />
              <p className="text-xs text-faint-foreground">The full steps are in SERVER.md in the {PRODUCT_NAME} folder.</p>
            </TabsContent>
          </Tabs>
        )}
      </OnboardingStep>

      <OnboardingStep n={3} title="Add the script to your pages">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">Copy to your coding agent</h3>
          <ToggleGroup type="single" variant="outline" size="sm" value={lang} onValueChange={(v) => v && setLang(v as keyof Setup["sentence"])} aria-label="Language">
            <ToggleGroupItem value="en">EN</ToggleGroupItem>
            <ToggleGroupItem value="zh">中文</ToggleGroupItem>
          </ToggleGroup>
        </div>
        <p className="text-sm text-muted-foreground">Open Claude Code or Codex in your website's code folder and paste this:</p>
        <CopyBlock text={setup.sentence[lang]} />
        <p className="text-xs text-faint-foreground">Your AI follows the steps {PRODUCT_NAME} prints, adds one script line to your pages, runs a self-check, and tells you what's left. Review its changes before you commit them.</p>
        <OrSeparator />
        <Tabs defaultValue="line" className="gap-3">
          <TabsList className="max-w-full overflow-x-auto">
            <TabsTrigger value="line"><Code aria-hidden />Script tag</TabsTrigger>
            <TabsTrigger value="terminal"><List aria-hidden />Terminal</TabsTrigger>
          </TabsList>
          <TabsContent value="line" className="flex flex-col gap-2">
            <p className="text-sm">Add this line to every page of your site, immediately before &lt;/head&gt;:</p>
            <CopyBlock text={initial.script_tag} />
          </TabsContent>
          <TabsContent value="terminal" className="flex flex-col gap-2">
            <p className="text-sm">In your website's code folder, run these commands and follow the instructions they print:</p>
            <CopyBlock text={setup.terminal} />
          </TabsContent>
        </Tabs>
        <p className="text-xs text-faint-foreground">Optional: your site's server can add information about each page request that only it sees. This is the Server half. The setup prints middleware for your framework. For details, see "The server half" in SERVER.md.</p>
      </OnboardingStep>

      <OnboardingStep n={4} title="Wait for the first visit">
        {first ? (
          <div className="flex flex-col gap-3">
            <Status tone="ok">First visit received</Status>
            <SessionRow s={first} compact />
            <div><Button onClick={onOpen}>Open dashboard</Button></div>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <Status tone="warn">No visits yet</Status>
            <p className="text-sm text-muted-foreground">Open a page of your site in your browser. The visit shows up here within a few seconds.</p>
          </div>
        )}
      </OnboardingStep>
    </OnboardingLayout>
  )
}
