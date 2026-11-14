// The JSON contract between cake's Python server and these pages: one response type per endpoint of /api.
// Each endpoint also has a JSON Schema in ./schema/ (the Python tests check cake's answers against it) and a sample
// answer in ./fixtures/ (served only by the screenshot and dev servers, never built into the release). `npm run
// check:ui` checks that every sample matches both its schema and its type here. web/README.md lists the endpoints.
//
// Conventions
// - Keys are snake_case, like PostHog 1.0's API and cake 0.3.4's /api/health.
// - Times inside a session are whole milliseconds from its start (`*_ms`); the pages format them ("1:36", "1m 36s").
// - Wall-clock times and days come formatted by the server in the owner's timezone ("Today 09:12", "Thu").
// - A session's shares are whole percents of its actions; counts are whole numbers; sizes are bytes or MB as named.
// - Text meant for the page (titles, reasons, the coverage table) comes in English, ready to show.
// - Any status other than 2xx carries an ApiErrorBody.

// ---------------------------------------------------------------- shared

/** Who acted in a session, one verdict each (DESIGN.md §3.1): a session cake can't tell counts as human, with
 *  evidence "thin" (its reasons say why). */
export type Verdict = "human" | "agent" | "bot"
/** A Human session cake couldn't tell (too few actions, a phone or tablet, evidence too weak or pointing both ways). */
export type Evidence = "thin"
/** Who acted during one stretch of a session or in one action ("unsure": the behavior model couldn't tell). */
export type Actor = "human" | "agent" | "unsure"
/** An Agent session from start to finish, or a human and an agent taking turns (hand-off points on its timeline). */
export type AgentTurns = "agent_only" | "human_agent"
/** How sure an agent's or a bot's name is: verified by a signature or a published address range; likely from
 *  the name it gives or the product's own traces; possible from its behavior alone. */
export type Certainty = "verified" | "likely" | "possible"
/** The date filter of the dashboard and the session list. */
export type DateRange = "today" | "7d" | "30d"

/** Share of a session's actions each actor took, in whole percents that add up to 100 (all 0 when the behavior model
 *  did not run, as for bots). */
export type Share = { human: number; agent: number; unsure: number }
/** One stretch of a session in which one actor acted. */
export type Segment = { who: Actor; start_ms: number; end_ms: number }
/** A moment control passed between a human and an agent. */
export type Handoff = { at_ms: number; to: "human" | "agent" }
/** Who acted when, over a whole session: drawn as the timeline under a replay. */
export type Timeline = { duration_ms: number; segments: Segment[]; handoffs: Handoff[] }

/** One session as every list shows it (sessions page, dashboard, the home page's examples). */
export type SessionSummary = {
  id: string
  verdict: Verdict
  /** "thin" for a Human session cake couldn't tell, which the pages mark; null otherwise. */
  evidence: Evidence | null
  /** Set for Agent sessions, null otherwise. */
  agent_turns: AgentTurns | null
  /** The agent's product or automation tool name (Claude in Chrome, Comet, Playwright…), or the program's name for a
   *  bot; null when no name fits an agent (the pages say Unnamed) and for sessions without an agent. */
  agent: string | null
  /** How sure the name is; null without a name. */
  certainty: Certainty | null
  /** When it started, formatted by the server ("Today 09:12"). */
  when: string
  /** How long its recording runs: the player's length (the session page's timeline.duration_ms). */
  duration_ms: number
  /** How many pages it went to: the rows of its page's Pages visited. */
  pages: number
  share: Share
  /** Who acted when, on the recording's clock; sent for every session the behavior model split into runs, so the row can
   *  draw its timeline. */
  segments?: Segment[]
}

/** Groups of sessions: the filters of the session list and their counts. all = human + agent + bot; agent splits into
 *  agent_only + human_agent (by agent_turns); thin counts the Human sessions on thin evidence. */
export type SessionGroup = "all" | Verdict | AgentTurns | Evidence
export type SessionCounts = Record<SessionGroup, number>

// ---------------------------------------------------------------- GET /api/overview?range=

export type OverviewQuery = { range?: DateRange }
/** One day of the "Estimated human and agent time" chart: each session's time split by the behavior model's shares, whole
 *  percents, labelled by the server ("Thu"). */
export type DayShare = { day: string; human: number; agent: number; unsure: number }
/** Sessions per agent name, Human + agent sessions included; name null: the agents no product name fits (Unnamed);
 *  bots never appear here. */
export type AgentCount = { name: string | null; sessions: number }
/** Visits to one page by agents and by humans: both "Pages … visit most" tables sort this one list. */
export type PageVisits = { path: string; agent: number; human: number }

/** What cake records and how it decides (dashboard bottom, the Bots "?"). Comes from agentcake/data/coverage.en.json
 *  and judging.en.json, so the pages never carry this wording. The names of the categories themselves
 *  are judging.en.json's too, read when the pages are built (src/lib/taxonomy.ts). */
export type Coverage = {
  title: string
  lead: string
  columns: { what: string; shown_as: string; how: string }
  rows: { what: string; verdict: Verdict; shown_as: string; how: string }[]
  bot: { question: string; answer: string }
}

export type Overview = {
  counts: SessionCounts
  /** Agent sessions over the same range a week earlier, for "+12 vs last week". */
  agent_last_week: number
  share_by_day: DayShare[]
  agents_seen: AgentCount[]
  top_pages: PageVisits[]
  /** The newest sessions of every kind, newest first (the server decides how many). */
  latest: SessionSummary[]
  /** The newest Agent sessions, newest first (the top block). */
  latest_agent: SessionSummary[]
  /** How long sessions last on average. */
  average_length: AverageLength
  /** The disk budget and what cake's data uses of it, whatever the filters: the dashboard's Disk bar. */
  storage: Storage
  coverage: Coverage
}

/** The settings page's disk numbers in one place (Settings.storage, budget_mb, auto_free): the dashboard warns from
 *  warn_at_pct, and says what happens when the budget is full by auto_free; disk and replays_stopped say why new
 *  replays stop while the disk is below its floor. */
export type Storage = {
  used_bytes: number; budget_mb: number; warn_at_pct: number; days_left: number | null; auto_free: boolean
  disk: Disk; replays_stopped: ReplaysStopped
}

/** The average length of a session, from its first to its last recorded action (a page opened, or the visitor's
 *  pointer, keys, wheel or touch), so a tab left open afterwards adds nothing. */
export type AverageLength = {
  /** Milliseconds by who visited: Human, Agent only and Human + agent; null when the range has no such session. */
  ms: { human: number | null; agent_only: number | null; human_agent: number | null }
  /** How the length is measured, in a sentence the dashboard can show (agentcake/data/coverage.en.json). */
  about: string
}

// ---------------------------------------------------------------- GET /api/sessions?verdict=&turns=&evidence=&agent=&range=&cursor=

/** verdict: one verdict; turns: an Agent session's split (keeps only Agent sessions); evidence: thin keeps the Human
 *  sessions cake couldn't tell; agent: an exact name from agent_names; they combine; cursor: `next` of the page before. */
export type SessionsQuery = { verdict?: Verdict; turns?: AgentTurns; evidence?: Evidence; agent?: string; range?: DateRange; cursor?: string }
export type SessionsPage = {
  /** Counts under the agent and range filters, whatever the verdict and turns filters. */
  counts: SessionCounts
  /** How many sessions every filter keeps. */
  total: number
  /** Agent names to filter by (named agents only). */
  agent_names: string[]
  /** Newest first. */
  results: SessionSummary[]
  /** Opaque cursor for the next page, or null on the last page. */
  next: string | null
  /** The most sessions one page holds. */
  page_size: number
}

// ---------------------------------------------------------------- GET /api/session/<id>

export type LayerId = "name" | "verify" | "environment" | "behavior"
/** What one layer concluded: a verdict, nothing found, or switched off here. */
export type LayerState = Verdict | "human_agent" | "unknown" | "no_hit" | "off"
/** The kind of evidence behind a reason; the page picks its icon. */
export type ReasonKind = "user_agent" | "server" | "page" | "browser" | "clicks" | "keys" | "motion" | "model"
/** A reason: what it means (text) and, under it, what was seen in technical words (detail), null when it has none. */
export type Reason = { kind: ReasonKind; tone: "human" | "agent" | "none"; text: string; detail: string | null }
/** One of the four layers of "Why this verdict", in the order name, verify, environment, behavior. leans: the side its
 *  evidence points to, and percent how sure it is of that side (1–99); both null when it judged nothing (no hit, off,
 *  too little data). */
export type LayerReasons = { layer: LayerId; state: LayerState; reasons: Reason[]; percent: number | null; leans: "agent" | "human" | "bot" | null }
/** One action in "Every action": what, never what was typed (inputs are masked), and the page it was taken on. */
export type Action = { at_ms: number; who: Actor; what: string; page: string }
/** One page of a session, in the order the pages opened: the first is where the visit came in, the last where it left
 * . A single-page app's new address is a new page. */
export type SessionPage = {
  /** Path and query, as cake keeps them. */
  path: string
  /** When the page opened, and how long the visit stayed: until the next page opened, the last page until the end. */
  at_ms: number
  duration_ms: number
  /** The visitor's actions on the page: "Every action" without its Open rows. */
  actions: number
  /** Who acted on the page, named as the session categories name it: a human only, an agent only, a human and an
   *  agent (Human + agent), or unknown when all its actions are; a page without actions takes who acted when it
   *  opened. */
  /** Who acted on it; null when no one did (a page without actions). */
  who: "human" | "agent" | "human_agent" | "unknown" | null
}
/** Why a replay is gone or cut short: deleted to free disk space ("When the budget is full, free space for me"; the
 *  verdict, timeline and server half stay), some events not stored while the disk budget was full, or nothing to
 *  replay (the visit sent no page events). */
export type ReplayMissing = "freed" | "dropped" | "none"
/** The replay's chunks (one per 10 seconds of activity), read one at a time from …/replay?chunk=<n>: the player
 *  reads the chunk it plays and the one after it, and the chunks before a moment it jumps to. */
export type ReplayInfo = {
  /** Where the player starts, and the address of the page at that moment. */
  start_ms: number
  start_url: string
  /** The session's ms 0 on the events' clock (epoch milliseconds): an event stamped T is at T − epoch_ms. */
  epoch_ms: number
  /** "Jump to hand-off" starts the player this long before a hand-off (a cake setting). */
  handoff_lead_ms: number
  /** Chunk n covers chunks[n], in time order; empty when there is nothing to replay. */
  chunks: { start_ms: number; end_ms: number }[]
  /** Why the replay is gone or cut short; null when it is all there. */
  missing: ReplayMissing | null
}

/** What the site's server saw of one page request: the server half's token (SERVER.md, agentcake/edge_token.py). */
export type ServerPage = {
  /** When the server saw the request. */
  at_ms: number
  path: string
  /** Sec-Fetch-Site, -Mode, -Dest and -User as the browser sent them; null for one it did not send. */
  fetch: { site: string | null; mode: string | null; dest: string | null; user: string | null }
  /** A signed request: its Signature-Agent and whether the signature verified; null when it was not signed. */
  signature: { agent: string | null; verified: boolean } | null
  /** Whether the request came from the network cake.js's uploads came from; null when cake can't tell. */
  same_network: boolean | null
  /** Whether cake.js's uploads sent the page request's User-Agent, and its Accept-Language; null when either side
   *  didn't say. */
  same_user_agent: boolean | null
  same_language: boolean | null
  /** How many more page views of the visit brought this page's token again: the browser showed them a stored copy
   *  (after a 304, or going back), so they have no server half of their own. */
  reuses: number
}
/** The network cake.js's uploads came from, as the load balancer saw it (server mode); never the address itself. */
export type Network = { country: string | null; range: string | null; ja4: string | null; protocol: string | null }
/** The "Server half" table of a session. */
export type ServerHalf = {
  /** One row per page request whose token arrived, in time order. */
  pages: ServerPage[]
  /** null on this computer, where every visit comes from 127.0.0.1. */
  network: Network | null
  /** Why pages are missing or there are none, in a sentence from cake; null when nothing needs saying. */
  note: string | null
}

export type SessionDetail = {
  session: SessionSummary
  /** Who acted, in one line ("A human, then Claude in Chrome, then the human again"). */
  title: string
  /** The verdict in a sentence or two, shown after the verdict's name. */
  summary: string
  /** How sure cake is of the verdict, in whole percents (1–99, calibrated): Human that a human acted, Agent that an
   *  agent did, Unknown that an agent did, Bot how far its name is verified; null when it doesn't say (judged before
   *  the percent was kept). */
  percent: number | null
  timeline: Timeline
  /** The pages in the order they opened; never empty. */
  pages: SessionPage[]
  layers: LayerReasons[]
  actions: Action[]
  replay: ReplayInfo
  server: ServerHalf
}

// ---------------------------------------------------------------- GET /api/session/<id>/replay?chunk=<n>

/** An rrweb event as recorded (timestamp in epoch milliseconds); the player reads the rest. */
export type ReplayEvent = { type: number; timestamp: number; data: Record<string, unknown> }
export type ReplayChunk = { chunk: number; start_ms: number; end_ms: number; events: ReplayEvent[] }

// ---------------------------------------------------------------- GET and POST /api/settings

/** Whether visits arrive from a source: shown as Receiving, Waiting or Not connected. */
export type Connection = "receiving" | "waiting" | "not_connected"
/** Where the website's visits arrive: this computer's AgentCake, or AgentCake installed on a server (server mode). */
export type Route = "this_computer" | "server"
/** The four layers that judge, and whether each runs here (verify only in server mode). Not settings. */
export type Layers = Record<LayerId, boolean>
/** The last log import of the site's web server: when, the log's format, and the recommended request headers its
 *  log lacks or leaves empty on every page request. */
export type LogImport = { last: string; format: string; missing: string[]; empty: string[] }

export type Settings = {
  /** The website's domain, "" until it is set; the key its page script sends (null before AgentCake first started). */
  site_domain: string
  site_key: string | null
  /** The line a site adds to its pages, with this AgentCake's address and the site key. */
  script_tag: string
  sources: { site: Connection; server_half: Connection }
  /** When each source last sent something, in the server's words ("Today 09:12"); null when it never did. */
  last_seen: { site: string | null; server_half: string | null }
  route: Route
  /** missing: request headers that none of the site's latest page requests brought its server (something in front of
   *  the server removes them); logs: the last log import, null before the first. */
  server_half: { missing: string[]; logs: LogImport | null }
  /** How often the open page asks for sources and last_seen again ("connected" within 10 seconds). */
  refresh_ms: number
  /** The agent and network lists in use (they come with each release): their date, how old they are, whether that is
   *  past max_age_days, and the command that downloads newer ones. */
  lists: { built: string; age_days: number; max_age_days: number; stale: boolean; update_command: string }
  /** 0 keeps everything. */
  retention_days: number
  retention_choices: number[]
  budget_mb: number
  budget_choices_mb: number[]
  auto_free: boolean
  /** days_left: when the budget is full at last week's pace; null when nothing was added last week. free_to_pct: the
   *  share of the budget freeing space brings cake's data down to (auto_free_target_ratio), as auto_free's
   *  description states it. */
  storage: { used_bytes: number; warn_at_pct: number; days_left: number | null; disk: Disk; replays_stopped: ReplaysStopped; free_to_pct: number }
  /** The page script's settings: watch the site's own document lookups; CSS selectors of parts of its pages never
   *  recorded, on top of cake.js's own private elements. */
  hook_dom: boolean
  hide_selectors: string
  layers: Layers
  database: { path: string; sessions: number }
}

/** POST body (Content-Type: application/json): only the fields to change; the answer is the whole Settings. */
export type SettingsUpdate = {
  retention_days?: number
  budget_mb?: number
  auto_free?: boolean
  site_domain?: string
  hook_dom?: boolean
  hide_selectors?: string
}

// ---------------------------------------------------------------- GET /api/setup

/** The home page's ways to connect (from `agentcake sentence` and `setup --print`) and its example preview. */
export type Setup = {
  /** The one sentence for a coding agent, in both languages of the toggle. */
  sentence: { en: string; zh: string }
  /** Commands for the Terminal and On a server tabs, one per line, placeholders only. */
  terminal: string
  server: string
  /** Shown as "example data" until real sessions arrive. */
  example: { sessions: SessionSummary[]; timeline: Timeline }
  /** Sessions the lists show, at any time, and how many are Agent sessions: until the first session, the home page and
   *  the dashboard show how to connect the website (like PostHog 1.0's overlay before the first event). */
  recorded: { sessions: number; agent: number }
}

// ---------------------------------------------------------------- GET and POST /api/register

/** Whether this data folder has registered with Tartini AI: until it has, the pages show the registration card
 *  before anything else. Also the answer to a POST that was sent. */
export type Registration = {
  registered: boolean
  /** What was sent, exactly as "See what is sent" showed it, and when (formatted by the server); null before. */
  sent: { body: string; when: string } | null
  /** The checks the card makes before its button turns on, the ones cake makes before it sends: the email address
   *  matches email_pattern as a whole and has at most email_max_chars characters; a company at most company_max_chars. */
  email_pattern: string
  email_max_chars: number
  company_max_chars: number
  /** Where to write to have a registration deleted (PRIVACY.md). */
  delete_contact: string
}

/** POST body (Content-Type: application/json): the registration exactly as the card's "See what is sent" shows it,
 *  JSON.stringify(payload, null, 2) with the keys in this order, company only when given. cake sends that text on
 *  unchanged (agentcake/register.py); a body in any other form is a 400. */
export type RegistrationPayload = { email: string; company?: string; product_updates: boolean; consent_version: string }

// ---------------------------------------------------------------- GET /api/health

/** Read by `agentcake doctor` and the install check (same fields as Agent Cake 0.3.4); the pages don't use it. */
export type Health = {
  ok: boolean
  version: string
  home: string
  site_key: string | null
  sessions: number
  real_sessions: number
  selfcheck_visits: number
  space: {
    used: number; budget: number; pct: number; days_left: number | null; warn: boolean; full: boolean; freed: number; auto_free: boolean
    disk: Disk
    replays_stopped: ReplaysStopped
  }
}

/** The disk that holds the data: bytes, and whether its free space is below the floor (disk_min_free_mb). */
export type Disk = { total: number; free: number; min_free: number; low: boolean }

/** Why new replays are not being stored, if they aren't: below the disk's floor with "free space for me" off; below
 *  it while other files fill the disk, so deleting every old replay would not make room and none was deleted;
 *  the disk budget is full. */
export type ReplaysStopped = "disk" | "disk_full_other" | "budget" | null

// ---------------------------------------------------------------- errors

/** The body of every answer that is not 2xx: what happened, in a sentence the page can show. */
export type ApiErrorBody = { error: string }
