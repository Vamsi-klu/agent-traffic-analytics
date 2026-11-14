// The registration step in front of the local dashboard (S5.8, D32; DESIGN.md §6.6): until this AgentCake has
// registered, every page shows the registration card first. The demo shop (/demo), collecting visits, the command line
// and doctor are not these pages and never ask. Data: GET /api/register; the card's button is the only thing that
// posts it. A registration that can't be sent lets the owner in for as long as this page stays open, and the card asks
// again the next time the dashboard is opened: nothing is retried, and nothing is kept in the browser.
import { useState, type ReactNode } from "react"
import { RegisterCard, type RegisterOutcome } from "@/components/cake/register-card"
import { Loaded } from "@/components/cake/page-state"
import { api, asApiError, useApi } from "@/data/api"
import type { Registration } from "@/data/types"
import { PRODUCT_NAME } from "@/lib/product"

/** The answers to a press that mean "fix what you typed", and "already registered, or another press is on its way". */
const BAD_REQUEST = 400, CONFLICT = 409

export function RegistrationGate({ children }: { children: ReactNode }) {
  const registration = useApi((signal) => api.registration(signal), [])
  const [through, setThrough] = useState(false)
  if (through) return <>{children}</>
  return (
    <Loaded state={registration} what={PRODUCT_NAME}>
      {(r) => (r.registered ? <>{children}</> : <RegisterStep rules={r} onThrough={() => setThrough(true)} />)}
    </Loaded>
  )
}

function RegisterStep({ rules, onThrough }: { rules: Registration; onThrough: () => void }) {
  const [outcome, setOutcome] = useState<RegisterOutcome>({ state: "ready" })
  const register = (body: string) => {
    setOutcome({ state: "sending" })
    api.register(body).then(onThrough, async (e: unknown) => {
      const error = asApiError(e)
      if (error.status === CONFLICT) {
        const now = await api.registration().catch(() => null)
        if (now?.registered) return onThrough() // registered from another tab meanwhile
      }
      setOutcome({ state: error.status === BAD_REQUEST || error.status === CONFLICT ? "invalid" : "not_sent", message: error.message })
    })
  }
  return <RegisterCard rules={rules} outcome={outcome} onRegister={register} onContinue={onThrough} />
}
