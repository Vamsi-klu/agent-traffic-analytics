// The project around every page (D40): the top bar with the website's address. Read once from /api/settings, as PostHog
// 1.0's App read its team's app_url once; the pages that save the domain (the onboarding, Settings) tell it the new one.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { AppShell } from "@/components/cake/app-shell"
import { ProjectLink } from "@/components/cake/project-link"
import { api } from "@/data/api"

const SetDomain = createContext<(domain: string) => void>(() => undefined)

/** For a page that saved site_domain: shows the new one in the top bar. */
export const useSetProjectDomain = () => useContext(SetDomain)

export function ProjectShell({ children }: { children: ReactNode }) {
  // undefined until /api/settings answers (nothing is shown rather than a guess), then the domain or null
  const [domain, setDomain] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    api.settings().then((s) => setDomain(s.site_domain || null), () => setDomain(undefined))
  }, [])
  return (
    <SetDomain.Provider value={(saved) => setDomain(saved || null)}>
      <AppShell project={domain === undefined ? null : <ProjectLink domain={domain} />}>{children}</AppShell>
    </SetDomain.Provider>
  )
}
