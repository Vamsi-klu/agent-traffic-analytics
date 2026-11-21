// Installed, no visits from the website yet: how to connect it, in two ways. First, one sentence for a coding agent,
// which points to the guide README's install sentence names (INSTALL.md): the agent looks at the website, decides where
// AgentCake runs, asks the owner, explains its plan and waits for their approval, then connects the website (`agentcake
// setup --print --site`, SERVER.md for a server) and checks it with doctor; or set it up by hand: 1 the
// website's address (site_domain, the project the top bar shows), 2 where AgentCake runs (a server for a public website,
// the default: on its own subdomain, the three things that takes, a server, a DNS record and its settings, each in plain
// words over its commands, SERVER.md for the rest; this computer for a site on it), 3 the page script, by hand or in a
// terminal, with the server middleware as an optional part. Under both, the website's first visit, asked for again every refresh_ms and shown when it
// comes, as PostHog 1.0's setup page asked "What URL will you be using PostHog on?", gave the snippet, and its
// dashboard waited under "Start sending events" until the first. Sessions an earlier AgentCake's demo shop recorded
// don't connect the website: the home page stays here until the website's own first session (recorded.site), and the
// dashboard shows the same page until the first session of any kind. Data: /api/setup and /api/settings; POST
// /api/settings saves the address.
import { useEffect, useState } from "react"
import { ChevronDown, ChevronUp, Code, List, Monitor, Plug, Server } from "lucide-react"
import { Navigate, useLocation, useNavigate } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { CopyBlock, DocumentLink, Status } from "@/components/cake/bits"
import { OnboardingLayout, OnboardingStep, OrSeparator } from "@/components/cake/onboarding"
import { Loaded } from "@/components/cake/page-state"
import { SessionRow } from "@/components/cake/session-row"
import { api, asApiError, useApi } from "@/data/api"
import type { SessionSummary, Settings, Setup } from "@/data/types"
import { PRODUCT_NAME } from "@/lib/product"
import { WORDS } from "@/lib/words"
import { useSetProjectDomain, useSetWebsiteConnected } from "@/pages/project"

const ON_SERVER = ["install", "dns", "settings"] as const // the order the subdomain route takes them in

export function HomePage() {
  const navigate = useNavigate()
  const { search, hash } = useLocation()
  // The dashboard keeps the address's query (#/?range=30d opens #/dashboard?range=30d) and any fragment after it.
  const dashboard = { pathname: "/dashboard", search, hash }
  const setup = useApi((signal) => api.setup(signal), [])
  return (
    <Loaded state={setup} what="the setup steps">
      {(s) => (s.recorded.site > 0 ? <Navigate to={dashboard} replace /> : <Onboarding setup={s} onOpen={() => navigate(dashboard)} />)}
    </Loaded>
  )
}

/** The four steps; onOpen: what "Go to dashboard" does once the first visit has come. */
export function Onboarding({ setup, onOpen }: { setup: Setup; onOpen: () => void }) {
  const settings = useApi((signal) => api.settings(signal), [])
  return <Loaded state={settings} what="your website's settings">{(s) => <Steps setup={setup} initial={s} onOpen={onOpen} />}</Loaded>
}

function Steps({ setup, initial, onOpen }: { setup: Setup; initial: Settings; onOpen: () => void }) {
  const [saved, setSaved] = useState(initial.site_domain)
  const [domain, setDomain] = useState(initial.site_domain)
  const [error, setError] = useState<string | null>(null)
  const [manual, setManual] = useState(false)
  const [first, setFirst] = useState<SessionSummary | null>(null)
  const setProjectDomain = useSetProjectDomain(), setConnected = useSetWebsiteConnected()
  // Step 4: asked again until the website's first session is there (within refresh_ms of its arrival); a session the
  // demo shop of an earlier AgentCake recorded isn't the website's.
  useEffect(() => {
    if (first) return undefined
    const timer = setInterval(() => {
      api.sessions({}).then((page) => {
        const fromSite = page.results.filter((s) => !s.demo_shop)
        if (fromSite.length) { setFirst(fromSite[fromSite.length - 1]); setConnected() }
      }, () => undefined)
    }, initial.refresh_ms)
    return () => clearInterval(timer)
  }, [first, initial.refresh_ms, setConnected])
  const save = () => api.saveSettings({ site_domain: domain }).then(
    (answer) => { setSaved(answer.site_domain); setDomain(answer.site_domain); setProjectDomain(answer.site_domain); setError(null) },
    (e: unknown) => setError(asApiError(e).message))
  const onServer = initial.route === "server"
  return (
    <OnboardingLayout
      status={<Badge variant="tag"><Plug aria-hidden />{PRODUCT_NAME} is running {onServer ? "on this server" : "on this computer"}</Badge>}
      title="Connect your website"
      example={setup.example}
    >
      <Card aria-labelledby="with-agent">
        <CardContent className="flex flex-col gap-3">
          <h2 id="with-agent" className="text-xl font-semibold minimal:text-lg minimal:font-bold">{WORDS.withAgentTitle}</h2>
          <p className="text-sm text-muted-foreground">{WORDS.withAgentHow}</p>
          <CopyBlock text={setup.sentence} />
          <p className="text-xs text-faint-foreground">{WORDS.withAgentWhat(PRODUCT_NAME)}</p>
        </CardContent>
      </Card>
      <OrSeparator />
      <div>
        <Button variant="outline" aria-expanded={manual} aria-controls="manual-steps" onClick={() => setManual(!manual)}>
          {manual ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}{WORDS.setUpManually}
        </Button>
      </div>
      {manual && (
        <div id="manual-steps" className="flex flex-col gap-6">
          <OnboardingStep n={1} title="Enter your website's address">
            <Label htmlFor="site-domain">Website domain</Label>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void save() }}>
              <Input id="site-domain" value={domain} placeholder="shop.example.com" onChange={(e) => setDomain(e.target.value)} aria-describedby="site-domain-about" />
              <Button type="submit" variant="outline" disabled={domain === saved}>Save</Button>
            </form>
            {error && <Alert variant="destructive"><AlertDescription>Unable to save your website address. {error}</AlertDescription></Alert>}
            <p id="site-domain-about" className="text-xs text-muted-foreground">{PRODUCT_NAME} still stores visits from other sites, but excludes them from the dashboard.</p>
          </OnboardingStep>

          <OnboardingStep n={2} title={`Choose where ${PRODUCT_NAME} runs`}>
            {onServer ? (
              <p className="text-sm">{PRODUCT_NAME} is running on this server. Visits from your site reach it through your site's domain.</p>
            ) : (
              <Tabs defaultValue="server" className="gap-3">
                <TabsList className="max-w-full overflow-x-auto">
                  <TabsTrigger value="server"><Server aria-hidden />On a server</TabsTrigger>
                  <TabsTrigger value="computer"><Monitor aria-hidden />On this computer</TabsTrigger>
                </TabsList>
                <TabsContent value="server" className="flex flex-col gap-4">
                  <p className="text-sm">You can't collect data from visitors to your public website if {PRODUCT_NAME} is only accessible on your computer. To collect their visit data, run {PRODUCT_NAME} on a server that can receive data from their browsers, then connect your website to it.</p>
                  {ON_SERVER.map((part) => (
                    <section key={part} className="flex flex-col gap-2" aria-labelledby={`on-server-${part}`}>
                      <h3 id={`on-server-${part}`} className="text-sm font-semibold">{WORDS.onServer[part].title}</h3>
                      <p className="text-sm">{WORDS.onServer[part].what(PRODUCT_NAME)}</p>
                      <CopyBlock text={setup.server[part]} />
                    </section>
                  ))}
                  <p className="text-xs text-faint-foreground">{WORDS.serverFullSteps} <DocumentLink path="SERVER.md" />.</p>
                </TabsContent>
                <TabsContent value="computer"><p className="text-sm">A website that runs on this computer, such as a development server on localhost, sends its visits to {PRODUCT_NAME} automatically, with no setup.</p></TabsContent>
              </Tabs>
            )}
          </OnboardingStep>

          <OnboardingStep n={3} title="Add the script to your pages">
            <Tabs defaultValue="line" className="gap-3">
              <TabsList className="max-w-full overflow-x-auto">
                <TabsTrigger value="line"><Code aria-hidden />Script tag</TabsTrigger>
                <TabsTrigger value="terminal"><List aria-hidden />Terminal</TabsTrigger>
              </TabsList>
              <TabsContent value="line" className="flex flex-col gap-2">
                <p className="text-sm">{WORDS.scriptWhere}</p>
                <CopyBlock text={initial.script_tag} />
              </TabsContent>
              <TabsContent value="terminal" className="flex flex-col gap-2">
                <p className="text-sm">In your website's project folder, run the following commands, and then follow the steps on the screen:</p>
                <CopyBlock text={setup.terminal} />
              </TabsContent>
            </Tabs>
            <p className="text-xs text-faint-foreground">Optional: The server middleware adds details about each page request that only your server can see. The setup prints the middleware for your framework. For more information, see <DocumentLink path="SERVER.md" />.</p>
          </OnboardingStep>
        </div>
      )}

      <OnboardingStep id="first-visit" title="Wait for the first visit">
        {first ? (
          <div className="flex flex-col gap-3">
            <Status tone="ok">First visit received</Status>
            <SessionRow s={first} compact />
            <div><Button onClick={onOpen}>Go to dashboard</Button></div>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <Status tone="warn">No visits yet</Status>
            <p className="text-sm text-muted-foreground">Open any page of your site in a browser. The visit appears in this step within a few seconds.</p>
          </div>
        )}
      </OnboardingStep>
    </OnboardingLayout>
  )
}
