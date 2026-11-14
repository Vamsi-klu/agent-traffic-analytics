// The registration card's words, the version of its text and the JSON it sends (S5.8, D32). The title, the subtitle,
// the two paragraphs, the two field names, the small print and the button are the user's own words (plan D32) and
// stay exactly as they are; the rest is ours. The version goes with every registration (consent_version), so it tells
// which text was shown: change it whenever any of these words change. cake checks the body and sends it on unchanged
// (agentcake/register.py), which is why the page builds it once, here, for both "See what is sent" and the button.
import type { Registration, RegistrationPayload } from "@/data/types"
import { PRODUCT_NAME } from "@/lib/product"

/** The day these words last changed (YYYY-MM-DD): sent as consent_version. */
export const CONSENT_VERSION = "2026-11-13"

export const REGISTER_WORDS = {
  title: `Welcome to ${PRODUCT_NAME}`,
  subtitle: "Free, open-source agent analytics",
  why: `${PRODUCT_NAME} is an open-source project. We're looking for early users to help shape what we build next.`,
  stays: "Register your installation to get started. Your website analytics and session recordings stay on your own server.",
  email: "Email address",
  company: "Company (optional)",
  updates: "Product update emails",
  updatesHint: "Every update email has an unsubscribe link.",
  smallPrint: "Your registration details will be sent to Tartini AI. No website traffic, session replay or product usage telemetry is sent.",
  seeWhatIsSent: "See what's sent",
  whatIsSent: "What's sent",
  button: "Register & Continue",
  emailHint: "Enter an email address like name@example.com.",
  notSentTitle: "Your registration wasn't sent",
  notSentNext: `${PRODUCT_NAME} kept nothing and won't retry sending your registration. It asks you to register again the next time you open it.`,
  invalidTitle: "Check what you entered",
  continue: "Continue",
}

/** What the card's fields hold. */
export type RegistrationFields = { email: string; company: string; productUpdates: boolean }
/** The checks GET /api/register hands the card: the ones cake makes before it sends. */
export type RegistrationRules = Pick<Registration, "email_pattern" | "email_max_chars" | "company_max_chars">

/** The text "See what is sent" shows and the button posts: JSON.stringify(payload, null, 2), the keys in the
 *  contract's order, spaces around the email and the company dropped, company only when given. */
export function registrationBody(fields: RegistrationFields): string {
  const email = fields.email.trim(), company = fields.company.trim()
  const payload: RegistrationPayload = {
    email,
    ...(company ? { company } : {}),
    product_updates: fields.productUpdates,
    consent_version: CONSENT_VERSION,
  }
  return JSON.stringify(payload, null, 2)
}

/** Whether an email address passes cake's check: the whole address matches email_pattern, within email_max_chars. */
export function emailOk(email: string, rules: RegistrationRules): boolean {
  const value = email.trim()
  return value.length > 0 && value.length <= rules.email_max_chars && new RegExp(`^(?:${rules.email_pattern})$`).test(value)
}
