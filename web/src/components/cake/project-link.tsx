// The project in the top bar: one AgentCake is one project, its website, as PostHog 1.0's team with its app_url.
// Its address opens the site in a new tab. Until it is set, "Set up your website": the four steps (the home page) while
// the website hasn't sent a session, as PostHog 1.0 sent its owner to its setup page; Settings ("Your website", where
// the address is set) once it has. On hover and on focus it says it opens in a new tab.
import { ExternalLink, Globe } from "lucide-react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { siteAddress } from "@/lib/format"
import { Hint } from "./bits"

export function ProjectLink({ domain, connected }: { domain: string | null; connected: boolean }) {
  if (!domain) {
    return <Button asChild variant="ghost" size="sm"><Link to={connected ? "/settings" : "/"}><Globe aria-hidden />Set up your website</Link></Button>
  }
  return (
    <Hint text={`Open ${domain} in a new tab`}>
      <Button asChild variant="ghost" size="sm">
        <a href={siteAddress(domain)} target="_blank" rel="noreferrer">
          <Globe aria-hidden /><span className="max-w-40 truncate">{domain}</span><ExternalLink aria-hidden />
        </a>
      </Button>
    </Hint>
  )
}
