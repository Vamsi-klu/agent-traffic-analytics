// The registration card the local dashboard shows before anything else until this AgentCake has registered
// (DESIGN.md §6.6). Its words are in src/lib/registration.ts. "See what is sent" shows the exact JSON the
// button posts; the button stays off until the email address passes cake's check. The page that shows the card does
// the asking (pages/register.tsx) and tells it how the last press went: being sent, not sent (say why, then Continue:
// no retry, the card asks again next time), or refused for what was typed (say why, keep the form).
import { useId, useState, type FormEvent } from "react"
import { ArrowRight, Braces, LoaderCircle, TriangleAlert } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { REGISTER_WORDS as W, emailOk, registrationBody, type RegistrationFields, type RegistrationRules } from "@/lib/registration"
import { Crumb } from "./crumb"

/** How the last press of the button went. */
export type RegisterOutcome =
  | { state: "ready" }
  | { state: "sending" }
  | { state: "not_sent"; message: string }
  | { state: "invalid"; message: string }

export function RegisterCard({ rules, outcome, onRegister, onContinue, initial }: {
  rules: RegistrationRules
  outcome: RegisterOutcome
  /** Called once per press with the text to post, the same text "See what is sent" shows. */
  onRegister: (body: string) => void
  /** After a registration that wasn't sent: into the dashboard anyway. */
  onContinue: () => void
  /** Filled-in fields, for the component overview. */
  initial?: Partial<RegistrationFields>
}) {
  const ids = useId()
  const [fields, setFields] = useState<RegistrationFields>({ email: "", company: "", productUpdates: false, ...initial })
  const [touched, setTouched] = useState(false)
  const [showSent, setShowSent] = useState(false)
  const body = registrationBody(fields)
  const valid = emailOk(fields.email, rules)
  const sending = outcome.state === "sending", notSent = outcome.state === "not_sent"
  const set = (change: Partial<RegistrationFields>) => setFields((f) => ({ ...f, ...change }))
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (valid && !sending && !notSent) onRegister(body)
  }
  const hintShown = touched && fields.email.trim() !== "" && !valid
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4">
      <Crumb pose="wave" className="w-28" title="Crumb waves hello" />
      <Card className="w-full">
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            <h1 className="text-3xl font-semibold">{W.title}</h1>
            <p className="text-lg leading-snug font-extrabold">{W.subtitle}</p>
          </div>
          <div className="flex flex-col gap-2 text-muted-foreground">
            <p>{W.why}</p>
            <p>{W.stays}</p>
          </div>
          <form className="flex flex-col gap-4" onSubmit={submit} noValidate aria-label={W.title}>
            <fieldset disabled={sending || notSent} className="flex min-w-0 flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${ids}-email`}>{W.email}</Label>
                <Input id={`${ids}-email`} type="email" required autoComplete="email" maxLength={rules.email_max_chars}
                  value={fields.email} onChange={(e) => set({ email: e.target.value })} onBlur={() => setTouched(true)}
                  aria-invalid={hintShown || undefined} aria-describedby={hintShown ? `${ids}-email-hint` : undefined} />
                {hintShown && <p id={`${ids}-email-hint`} className="text-xs text-destructive">{W.emailHint}</p>}
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${ids}-company`}>{W.company}</Label>
                <Input id={`${ids}-company`} autoComplete="organization" maxLength={rules.company_max_chars}
                  value={fields.company} onChange={(e) => set({ company: e.target.value })} />
              </div>
              <div className="flex items-start gap-3">
                <Checkbox id={`${ids}-updates`} className="mt-0.5" checked={fields.productUpdates}
                  onCheckedChange={(on) => set({ productUpdates: on === true })} aria-describedby={`${ids}-updates-hint`} />
                <div className="flex flex-col gap-1">
                  <Label htmlFor={`${ids}-updates`}>{W.updates}</Label>
                  <p id={`${ids}-updates-hint`} className="text-xs text-muted-foreground">{W.updatesHint}</p>
                </div>
              </div>
            </fieldset>
            <p className="text-xs text-faint-foreground">{W.smallPrint}</p>
            {outcome.state === "invalid" && (
              <Alert variant="destructive"><TriangleAlert aria-hidden /><AlertTitle>{W.invalidTitle}</AlertTitle><AlertDescription>{outcome.message}</AlertDescription></Alert>
            )}
            {notSent && (
              <Alert variant="warn"><TriangleAlert aria-hidden /><AlertTitle>{W.notSentTitle}</AlertTitle><AlertDescription>{outcome.message} {W.notSentNext}</AlertDescription></Alert>
            )}
            <div className="flex flex-wrap items-center gap-3">
              {notSent
                ? <Button type="button" onClick={onContinue}>{W.continue}<ArrowRight aria-hidden /></Button>
                : <Button type="submit" disabled={!valid || sending} aria-busy={sending || undefined}>{sending && <LoaderCircle className="animate-spin" aria-hidden />}{W.button}</Button>}
              <Button type="button" variant="link" size="sm" aria-expanded={showSent} aria-controls={`${ids}-sent`} onClick={() => setShowSent((open) => !open)}>
                <Braces aria-hidden />{W.seeWhatIsSent}
              </Button>
            </div>
            {showSent && (
              <Card id={`${ids}-sent`} variant="sunk" size="sm" aria-label={W.whatIsSent}>
                <CardContent><pre className="font-mono text-xs break-words whitespace-pre-wrap">{body}</pre></CardContent>
              </Card>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
