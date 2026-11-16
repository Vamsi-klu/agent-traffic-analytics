// The registration card's words, the version of its text and the JSON it sends. The subtitle and the first paragraph
// are the owner's own words, as the owner wrote them; the title, the second paragraph, the two field names, the small
// print and the button began as the owner's own words, rewritten in Microsoft Clarity's voice with their meaning
// unchanged. The version goes with every registration (consent_version), so it tells which text was shown: change it
// whenever any of these words change. cake checks the body and sends it on unchanged (agentcake/register.py), which is
// why the page builds it once, here, for both "View registration data" and the button.
import type { Registration, RegistrationPayload } from "@/data/types"
import { PRODUCT_NAME } from "@/lib/product"

/** The day these words last changed (YYYY-MM-DD): sent as consent_version. */
export const CONSENT_VERSION = "2026-11-15"

export const REGISTER_WORDS = {
  title: `Welcome to ${PRODUCT_NAME}`,
  subtitle: "Free, open-source agent analytics",
  why: `${PRODUCT_NAME} is an open-source project. We're looking for early users to help shape what we build next.`,
  stays: "To get started, register your installation. Your website analytics and session recordings are stored on your own server.",
  email: "Email address",
  company: "Company (optional)",
  updates: "Product update emails",
  updatesHint: "Every update email includes an unsubscribe link.",
  smallPrint: `Only your registration details are sent to Tartini AI. ${PRODUCT_NAME} doesn't send website traffic, session replays, or product usage telemetry.`,
  seeWhatIsSent: "View registration data",
  whatIsSent: "Registration data",
  button: "Register and continue",
  emailHint: "Enter a valid email address, such as name@example.com.",
  notSentTitle: "Registration not sent",
  notSentNext: `${PRODUCT_NAME} doesn't keep your details or retry the registration. The registration form appears the next time you open ${PRODUCT_NAME}.`,
  invalidTitle: "Check your entries",
  continue: "Continue",
}

/** What the card's fields hold. */
export type RegistrationFields = { email: string; company: string; productUpdates: boolean }
/** The checks GET /api/register hands the card: the ones cake makes before it sends. */
export type RegistrationRules = Pick<Registration, "email_pattern" | "email_max_chars" | "company_max_chars">

/** The text "View registration data" shows and the button posts: JSON.stringify(payload, null, 2), the keys in the
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
