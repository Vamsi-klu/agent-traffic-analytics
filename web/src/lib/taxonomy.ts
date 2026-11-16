/** The session categories, as agentcake/data/judging.en.json names them, read when the pages are built
 *  (vite.config.ts), so every page, badge and filter says the same word as the API and the categories block:
 *  1 a verdict for each session (Human, Agent, Bot), a Human session cake couldn't tell marked thin evidence, an Agent
 *  session split into Agent only and Human + agent; 2 which agent: its product's or tool's name and how sure it is, or
 *  Unnamed. A stretch the behavior model couldn't tell is unsure ("Unknown" in bars, timelines and layers). */
import type { AgentTurns, Certainty, Evidence, Verdict } from "@/data/types"

/** One category: its name and a sentence on what it means. */
export type Category = { label: string; about: string }
export type Taxonomy = {
  title: string
  /** Which visits get a session at all, and which crawlers never do: the paragraphs under the categories block. */
  counted: string[]
  verdicts: Record<Verdict, Category>
  unsure: Category
  evidence: Record<Evidence, Category>
  turns: Record<AgentTurns, Category>
  names: Record<Certainty | "unnamed", Category>
}

export const TAXONOMY: Taxonomy = import.meta.env.VITE_TAXONOMY

/** In the order the filters, the top block and the categories block list them. */
export const VERDICT_ORDER: Verdict[] = ["human", "agent", "bot"]
export const TURNS_ORDER: AgentTurns[] = ["agent_only", "human_agent"]

/** The word for an agent no product name fits. */
export const UNNAMED = TAXONOMY.names.unnamed.label
