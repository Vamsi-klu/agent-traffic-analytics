// The interface's own wording, in one place (DESIGN.md §2). Visitors are Human / Agent / Unknown / Bot, never person,
// people or user; the names of the categories themselves are src/lib/taxonomy.ts's (judging.en.json). Text that comes
// with the data (session titles, reasons, the coverage table) is not here: it comes from /api.
import type { DateRange } from "@/data/types"

export const WORDS = {
  agentSessions: "Agent sessions",
  actedForHuman: "Sessions where an AI agent acted on behalf of a human",
  rowMarker: "An AI agent acted for a human",
  aHuman: "A human",
  botRow: "Bot sessions are counted but don't show a timeline.",
  withAgentTitle: "Install with your AI agent",
  withAgentHow: "Open Claude Code or Codex in your website's project folder, and then paste the following prompt:",
  setUpManually: "Install manually",
  scriptWhere: "Paste this line once, before the closing </head> tag in the layout or template that every page uses. For separate HTML files, add the line to each file.",
  dashboard: "Dashboard",
  keyMetrics: "Key metrics",
  deepDive: "Deep dive",
  sessionsPage: "Session replay",
  watchReplays: "Watch replays",
  whoUnknown: "Actor not identified",
  agentsByName: "Agents by name",
  eitherTurns: "All agent sessions",
  allHumanSessions: "All human sessions",
  withThinEvidence: "with limited evidence",
  paths: "Paths",
  path: "Path",
  sessionsGroup: "Sessions",
  visitorsGroup: "Visitors",
  pageViewsGroup: "Page views",
  botsNotInChart: "Bot sessions are counted separately and are excluded from this chart.",
  activeTime: "active time spent",
  pagesPerSession: "pages per session",
  session: "session",
  sessions: "sessions",
  totals: "Sessions, visitors, page views, active time spent, and pages per session",
  allFromDemoShop: "All sessions are from the demo shop",
  visitors: "visitors",
  noVisitorIds: "No visitor IDs in the selected date range",
  visitorsAre: "Each visitor is identified by a random ID that the page script stores in their browser for one year after their last visit.",
  outOfTotalTime: (total: string) => `of ${total} min total time`,
  pageViews: "page views",
  noSessionsInRange: "No sessions in the selected date range",
  noAgentSessionsInRange: "No Agent sessions in the selected date range",
  chart: "chart",
  agentsChart: "Top agents",
  agentsChartLead: "This chart shows the selected metric for each agent's sessions, with or without a human.",
  demoShop: "Demo shop",
  demoShopAbout: "This session was recorded in the demo shop, not on your website.",
  notConnectedTitle: "Your website isn't connected yet",
  notConnectedDemo: "The sessions on this page come from the demo shop, not your website.",
  connectWebsite: "Connect your website",
  layerLocalOrServer: "Local or server",
  layerServerOnly: "Server only",
  trends: "Trends",
  metric: "Metric",
  intervals: { hour: "Hour", day: "Day" },
  /** The note under Trends: the time zone its days and hours are in, as /api/web names it ("PST", "UTC+05:45"). */
  timesIn: (zone: string) => `Times in ${zone}`,
  /** The Agent block's comparison, PostHog's words for its previous period: as long as the range, right before it. */
  vsPrior: (n: number) => `vs. ${n} prior`,
  timeZone: "Time zone",
  timeZoneAbout: "Dates and times on the dashboard and in Session replay use this time zone.",
  /** The time zone choice that follows the computer or server AgentCake runs on: its IANA name and its abbreviation
   *  ("This computer's time zone (America/Los_Angeles, PST)"), the abbreviation alone when nothing names it. */
  followMachine: (where: string, name: string | null, short: string) =>
    `${where}'s time zone (${name && name !== short ? `${name}, ${short}` : short})`,
  searchTimeZones: "Search time zones",
  noTimeZoneMatches: "No time zone matches your search.",
  showAsTable: "Show as table",
  hideTable: "Hide table",
  toAgent: "Hand-off to agent",
  toHuman: "Hand-off to human",
  replayLoading: "Loading replay…",
  replayFailed: "Couldn't load the replay.",
  replayFreed: "This replay was deleted to free up disk space. You can still see the session's classification and timeline.",
  replayDropped: "Part of this replay wasn't saved because the disk space limit was reached at the time.",
  replayNone: "There's nothing to replay because this visit didn't send any page events.",
  replayWaiting: "Loading the next part…",
  replayNoPage: "No page content was recorded at this point. The replay shows only pointer movements and clicks.",
  replayPosition: "Replay position",
  /** What Crumb's drawing is to a screen reader where it stands for a state. */
  crumb: { loading: "Loading illustration", error: "Error illustration", empty: "Empty state illustration" },
  jumpToHandoff: "Jump to hand-off",
  pagesVisited: "Pages visited",
  noActions: "No actions recorded",
  entryPage: "Entry page",
  exitPage: "Exit page",
  serverHalf: "Server middleware",
  serverHalfLead: "This shows what the server middleware on your site reported for each page request.",
  serverHalfNone: "None of the page requests in this session include data from your site's server middleware.",
  layerOff: "This layer wasn't used to classify this session.",
  layerNoHit: "This layer found no evidence for this session.",
  shareOfActions: "Share of actions:",
  web: {
    titles: { sources: "Sources", devices: "Devices", geography: "Geography" },
    dimensions: {
      channel: "Channel", referring_domain: "Referring domain", utm_source: "UTM source", utm_medium: "UTM medium",
      utm_campaign: "UTM campaign", device_type: "Device type", browser: "Browser", os: "OS", country: "Country",
      region: "Region", city: "City", timezone: "Time zone", language: "Language",
    },
    breakdown: "Break down by",
    notSet: "Not set",
    direct: "No referrer",
    showAll: (n: number) => `Show all ${n}`,
    showFewer: "Show fewer",
    all: "All",
    kind: "Session type",
    agentShare: "Agent sessions %",
    split: (metric: string, agent: string, human: string) => `${metric}: ${agent}, ${human}`,
    noKind: (kind: string) => `No ${kind} sessions in the selected date range`,
    removeFilter: "Remove filter",
    watch: (value: string) => `View sessions for ${value} in Session replay`,
    serverOnly: (product: string) => `Country, region, and city data is available only when ${product} runs on a server.`,
    botsNote: "This table includes Agent and Human sessions only. Bot sessions aren't counted.",
  },
  /** What each dashboard card shows, behind its information icon (Clarity's own words stay in CLARITY), written as
   *  Clarity writes its tooltips. */
  about: {
    agents: ["This is the number of sessions where an AI agent acted on your site, alone or together with a human."],
    visitors: "This is the number of unique visitors to your site during the selected period of time.",
    pageViews: ["This is the number of pages viewed on your site during the selected period of time, including repeated views of the same page."],
    pagesPerSession: ["This is the average number of pages viewed in a session."],
    trends: ["This chart shows how the selected metric changes over time for Human and Agent sessions."],
    paths: "This table shows the pages visited during the selected period of time, with the sessions, visitors, and page views for each page.",
    sources: "This table shows where your sessions come from, by channel, referring domain, or UTM parameter.",
    devices: "This table shows the device types, browsers, and operating systems used in your sessions.",
    geography: "This table shows where your sessions come from, by country, region, city, time zone, or language.",
    agentShare: "When All is selected, the last column shows the percentage of sessions that are Agent sessions.",
  },
}

/** Microsoft Clarity's own definitions of its dashboard's metrics, word for word (the owner asked for Clarity's words):
 *  Sessions without its sentence on bots, which AgentCake counts. Clarity defines no other metric the dashboard shows. */
export const CLARITY = {
  sessions: ["This is the number of visits to your site during the selected period of time."],
  activeTime: ["This is the average time spent in a session", "Active time: When a user's attention was on your site",
    "Inactive time: When your site was hidden behind other tabs or windows"],
}

/** A total's name, the metric alone: "Sessions", "Active time spent". */
export const metricName = (unit: string) => unit.charAt(0).toUpperCase() + unit.slice(1)

/** "1 session", "28 sessions": a count of sessions, the noun in the right number. */
export const sessionCount = (n: number) => `${n} ${n === 1 ? WORDS.session : WORDS.sessions}`

/** The date filter's choices, in menu order. */
export const RANGES: Record<DateRange, string> = { "24h": "Last 24 hours", "7d": "Last 7 days", "30d": "Last 30 days", all: "All time" }

