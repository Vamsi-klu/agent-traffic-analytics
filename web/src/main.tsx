import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { HashRouter, Route, Routes } from "react-router"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ComponentsPage } from "@/pages/components"
import { HomePage } from "@/pages/home"
import { RegistrationGate } from "@/pages/register"
import { ProjectShell } from "@/pages/project"
import { pages } from "@/pages/registry"
import "./index.css"

// Light / dark follows the system; ?theme=dark|light forces one (used by screenshots).
const forced = new URLSearchParams(location.search).get("theme")
const media = matchMedia("(prefers-color-scheme: dark)")
const apply = () => document.documentElement.classList.toggle("dark", forced ? forced === "dark" : media.matches)
apply()
media.addEventListener("change", apply)

// The bundled fonts first (local files: milliseconds). Charts measure their labels once and keep the size, so they
// must measure in the real font whenever their data arrives; and nothing reflows when the fonts land. A font that
// fails to load just leaves the fallback font.
await Promise.allSettled([...document.fonts].map((face) => face.load()))

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider>
      <HashRouter>
        <ProjectShell>
          <RegistrationGate>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/components" element={<ComponentsPage />} />
              {pages.map((p) => <Route key={p.path} path={p.path} element={p.element} />)}
            </Routes>
          </RegistrationGate>
        </ProjectShell>
      </HashRouter>
    </TooltipProvider>
  </StrictMode>,
)
