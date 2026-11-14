// Top bar + page frame. Navigation uses Button (ghost; outline for the current page); `project` is the website's link
// beside the logo (D40, ProjectLink). DESIGN.md §6
import type { ReactNode } from "react"
import { Activity, List, Settings } from "lucide-react"
import { Link, NavLink } from "react-router"
import { Button } from "@/components/ui/button"
import { PRODUCT_NAME } from "@/lib/product"
import { CrumbHead } from "./crumb"

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: Activity },
  { to: "/sessions", label: "Sessions", icon: List },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function AppShell({ project, children }: { project?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-svh overflow-x-clip">
      <header className="sticky top-0 z-10 border-b-2 border-line bg-background">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2">
          <Link to="/" className="flex items-center gap-2 font-heading text-2xl font-bold">
            <CrumbHead className="size-9" /><span className="max-sm:hidden">{PRODUCT_NAME}</span>
          </Link>
          {project}
          <nav aria-label="Main" className="ml-auto flex gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to !== "/sessions"}>
                {({ isActive }) => (
                  <Button asChild variant={isActive ? "outline" : "ghost"} size="default">
                    <span aria-current={isActive ? "page" : undefined}><Icon aria-hidden /><span className="max-sm:sr-only">{label}</span></span>
                  </Button>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 pt-6 pb-16">{children}</main>
    </div>
  )
}
