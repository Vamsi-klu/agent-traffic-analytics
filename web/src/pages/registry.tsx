// The app's pages besides home and the component overview.
import type { ReactElement } from "react"
import { DashboardPage } from "./dashboard"
import { HomePage } from "./home"
import { SessionPage } from "./session"
import { SessionsPage } from "./sessions"
import { SettingsPage } from "./settings"

export const pages: { path: string; element: ReactElement }[] = [
  { path: "/dashboard", element: <DashboardPage /> },
  { path: "/sessions", element: <SessionsPage /> },
  { path: "/sessions/:id", element: <SessionPage /> },
  { path: "/settings", element: <SettingsPage /> },
  { path: "*", element: <HomePage /> },
]
