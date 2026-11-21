// Top bar + page frame. Navigation uses Button (ghost; outline for the current page); `project` is the website's link
// beside the logo (ProjectLink); the Style menu sits at the bar's end (StyleMenu, DESIGN.md §17). DESIGN.md §6. In
// Minimal the pages are tabs, the current one underlined.
import type { ReactNode } from "react"
import { Activity, List, Settings } from "lucide-react"
import { Link, NavLink } from "react-router"
import { Button } from "@/components/ui/button"
import { PRODUCT_NAME } from "@/lib/product"
import { WORDS } from "@/lib/words"
import { CrumbHead } from "./crumb"
import { StyleMenu } from "./style-menu"

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: Activity },
  { to: "/sessions", label: WORDS.sessionsPage, icon: List },
  { to: "/settings", label: "Settings", icon: Settings },
]

/** Minimal's top bar items: as tall as the bar, no frame, the current page underlined at the bar's foot. */
const NAV_MINIMAL = "minimal:h-auto minimal:self-stretch minimal:rounded-none minimal:border-x-0 minimal:border-t-0 minimal:border-b-3 minimal:border-b-transparent minimal:bg-transparent minimal:px-3 minimal:font-medium minimal:text-muted-foreground minimal:hover:bg-muted minimal:hover:text-foreground minimal:aria-[current=page]:border-b-foreground minimal:aria-[current=page]:font-semibold minimal:aria-[current=page]:text-foreground"

export function AppShell({ project, children }: { project?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-svh overflow-x-clip">
      <header className="sticky top-0 z-10 border-b-2 border-line bg-background minimal:border-b minimal:bg-card">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2 minimal:min-h-14 minimal:py-0">
          <Link to="/" className="flex items-center gap-2 font-logo text-2xl font-bold">
            <CrumbHead className="size-9" /><span className="max-sm:hidden">{PRODUCT_NAME}</span>
          </Link>
          {project}
          <nav aria-label="Main" className="ml-auto flex gap-1 minimal:self-stretch">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to !== "/sessions"} className="minimal:flex">
                {({ isActive }) => (
                  <Button asChild variant={isActive ? "outline" : "ghost"} size="default" className={NAV_MINIMAL}>
                    <span aria-current={isActive ? "page" : undefined}><Icon aria-hidden /><span className="max-sm:sr-only">{label}</span></span>
                  </Button>
                )}
              </NavLink>
            ))}
          </nav>
          <StyleMenu />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pt-6 pb-16">{children}</main>
    </div>
  )
}
