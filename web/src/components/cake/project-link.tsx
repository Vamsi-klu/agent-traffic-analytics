// The project in the top bar: one AgentCake is one project, its website, as PostHog 1.0's team with its app_url.
// Its address opens the site in a new tab; until it is set, a link to where it is set (Settings, "Your website").
import { ExternalLink, Globe } from "lucide-react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { siteAddress } from "@/lib/format"

export function ProjectLink({ domain }: { domain: string | null }) {
  if (!domain) {
    return <Button asChild variant="ghost" size="sm"><Link to="/settings"><Globe aria-hidden />Set up your website</Link></Button>
  }
  return (
    <Button asChild variant="ghost" size="sm">
      <a href={siteAddress(domain)} target="_blank" rel="noreferrer" title={`Open ${domain} in a new tab`}>
        <Globe aria-hidden /><span className="max-w-40 truncate">{domain}</span><ExternalLink aria-hidden />
      </a>
    </Button>
  )
}
