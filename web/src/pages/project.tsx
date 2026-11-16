// The project around every page: the top bar with the website's address. Read once from /api/settings, as PostHog
// 1.0's App read its team's app_url once; the pages that save the domain (the onboarding, Settings) tell it the new one.
// Until the website has sent a session (/api/setup's recorded.site), "Set up your website" opens the four steps; the
// onboarding tells it when the first session arrives.
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { AppShell } from "@/components/cake/app-shell"
import { ProjectLink } from "@/components/cake/project-link"
import { api } from "@/data/api"

const Project = createContext<{ setDomain: (domain: string) => void; setConnected: () => void }>({
  setDomain: () => undefined, setConnected: () => undefined,
})

/** For a page that saved site_domain: shows the new one in the top bar. */
export const useSetProjectDomain = () => useContext(Project).setDomain
/** For the page that saw the website's first session: the top bar's "Set up your website" then opens Settings. */
export const useSetWebsiteConnected = () => useContext(Project).setConnected

export function ProjectShell({ children }: { children: ReactNode }) {
  // undefined until /api/settings answers (nothing is shown rather than a guess), then the domain or null
  const [domain, setDomain] = useState<string | null | undefined>(undefined)
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    api.settings().then((s) => setDomain(s.site_domain || null), () => setDomain(undefined))
    api.setup().then((s) => setConnected(s.recorded.site > 0), () => setConnected(false))
  }, [])
  // one value for the shell's life, so the pages that hold its functions don't start over when the top bar changes
  const project = useMemo(() => ({ setDomain: (saved: string) => setDomain(saved || null), setConnected: () => setConnected(true) }), [])
  return (
    <Project.Provider value={project}>
      <AppShell project={domain === undefined ? null : <ProjectLink domain={domain} connected={connected} />}>{children}</AppShell>
    </Project.Provider>
  )
}
