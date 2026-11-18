# Changelog

Every release of AgentCake, newest first. Each release's files and their `SHA256SUMS` are on
[GitHub Releases](https://github.com/tartini-ai/agent-traffic-analytics/releases).

## 0.5.1

Last 24 hours replaces Today, dates and times follow a time zone you can choose, and the date ranges and their
comparison work as PostHog's web analytics does.

### Dashboard

- **Last 24 hours replaces Today** in the date filter of the dashboard and the session list. Today counted from
  midnight in the server's time zone: on a server set to UTC it started over late in the afternoon in California, and
  showed 0 until new sessions came. Last 24 hours runs from the start of the hour 24 hours ago to now. Last 7 days is
  still the default, and a link to the old Today range opens on it.
- **Time zone**: a new setting, in Settings or `agentcake config set timezone America/Los_Angeles`, for every date and
  time on the dashboard and in Session replay: where a day starts, the hours and days of Trends, and words such as
  Today 21:12. By default AgentCake follows the time zone of the computer or server it runs on, as before. A note under
  Trends names the time zone in use ("Times in PST").
- **Last 7 days and Last 30 days** start at midnight 7 and 30 days ago, as PostHog's do, so they hold 8 and 31 days,
  today's included. Their numbers can be larger than before.
- **Agent sessions** compares each range with its previous period, as long as the range and right before it, as
  PostHog does: the change, and the previous count ("+12", "vs. 30 prior"). It compared with a week earlier before.
- **Trends** shows Last 24 hours by hour, from the hour 24 hours ago to the current one, each hour with its date
  ("Nov 15, 23:00"). All time is by day now, as the last 7 and 30 days are; a range that crosses a new year names the
  year in its days ("Nov 3, 2025"). Its time axis names the hours or days at an even step: every 3 hours for Last 24
  hours, every day for Last 7 days, every 3 days for Last 30 days, and each month for All time ("Nov 2026"). On a
  narrow screen, where the labels would touch, the step doubles, and All time names quarters or years. Hovering still
  shows each hour or day.

### Command line

- `agentcake doctor` writes the time of the last log import in AgentCake's time zone, and names it.

### Local API

- `range=24h` takes the place of `range=today` on `/api/overview`, `/api/web` and `/api/sessions`, which now answer
  `range=today` with 400, as for any unknown range.
- `/api/overview`'s `agent_last_week` is `agent_earlier`: the Agent sessions of the range's previous period.
- `/api/web` says the time zone of its days and hours (`time_zone`), `/api/settings` reads and saves `timezone`, and
  `/api/timezones` lists the time zones that Settings offers.
- `/api/web`'s `trends` gives each point's hour or day as `key`, and how often the time axis names one as `every` (a
  number of points, or `month`).

## 0.5.0

The first public release: the repository is public, and the release's wheel is on PyPI. The browsers built into AI
apps now name the browser without deciding who acted, Antigravity's in-app browser is recognized, the bundled lists are
new, a site that records its own console no longer looks like a debugging connection, and the release files carry only
what an installation runs.

### Install

- **A public repository**: the release downloads with curl, without a GitHub sign-in. [`README.md`](README.md) and
  [`INSTALL.md`](INSTALL.md) no longer describe the private preview's download with the GitHub CLI.
- **PyPI**: when a release is published, `.github/workflows/pypi.yml` checks the release's wheel against its
  `SHA256SUMS` and uploads that wheel, and nothing else, to PyPI as `agentcake`, with Trusted Publishing and no token.
- README's pictures and links name their files at the release's tag, so the README shows the same on GitHub and on
  PyPI.

### Detection

- **The browsers built into AI apps only name the browser**: the in-app browsers of Antigravity, Codex and Cursor,
  ChatGPT Desktop, Claude Desktop and PostHog Desktop are browsers that people also use by hand. Their name, from the
  User-Agent or from a product rule, no longer makes a session Agent or Human + agent by itself. Automation traces and
  behavior decide who acted, as in any other browser, and the browser's name is the agent's when the session is Agent
  or Human + agent. When another product rule names the agent in such a browser, such as ChatGPT for Chrome's badge,
  the session names that agent instead of saying that its names disagree. Sessions in Codex's in-app browser keep their
  class and name, and some show a lower percent.
- **Antigravity in-app browser**: recognized by the `Antigravity/<version>` that ends its User-Agent, in every version.
  Its list of browser brands, which names only Chromium, no longer counts as an automation trace there.
- **Debugging connections**: the page script's check for a DevTools-protocol client now logs in a hidden frame of its
  own, which it removes at once. A site's own console recorder (rrweb's console plugin, analytics and error trackers)
  reads what the page logs, as such a client does, so every visitor of that site matched the check; a client with
  Runtime enabled still does. Sessions recorded by an earlier page script are judged as before. On a page whose
  sandbox policy keeps the frame apart, the check doesn't run.
- **Bundled lists, built on 2026-11-16**: HatchFeed, which ai.robots.txt lists as the link-preview fetcher of Meta's
  Muse, is a new name. On a server, OAI-AdsBot is verified against OpenAI's published addresses, and a visitor that
  calls itself OAI-AdsBot from anywhere else is an impersonation, as with GPTBot and OAI-SearchBot. Claude-Agent's
  entry follows Anthropic's own documentation.

### Evaluation

- **A website's own labelled sessions, held out**: given a copy of a website's data folder (with its `config.json`, so
  that a server's sessions are judged as on a server) and a list of its sessions whose answers you know, `agentcake eval
  --site-home <folder> --truth-site <list>` counts them on their own, in the sessions table and the scoreboard's
  held-out lines, and in no pooled rate, calibration or threshold ([`eval/README.md`](eval/README.md)).
- A rate in the report says how many sessions it left out as too little data, and A2 says, as A1 does, that A8 counts
  them.
- The figures in [`eval/README.md`](eval/README.md) are counted again with this release's code. They are unchanged,
  except that 5 sessions in Antigravity's in-app browser are now too little data instead of Not sure.

### Fixes

- **Help for one command**: `--help` or `-h` after a command prints its help and runs nothing. Before, `agentcake start
  --help` started AgentCake, `agentcake stop --help` stopped it and `agentcake ping --help` sent a test visit. A word a
  command doesn't take, or an option without its value, now stops it before anything runs, and the error names the
  word or the option.
- **The documents a sentence names**: where the command line, the API or the local pages name `SERVER.md` or
  `PRIVACY.md`, they give its address in the repository at this version's tag. An installation from the wheel or
  `agentcake.pyz` doesn't carry these files, so a coding agent couldn't find them.
- **An address that can't be read**, such as one with an unclosed IPv6 bracket, no longer stops a session from being
  judged or a server's log lines from being matched: the page view is matched by its time alone, as one without an
  address. A request whose target can't be read gets a 400 on both listeners instead of no answer, and a mistyped
  `register_url` of that kind is reported as unreachable, as any other address that isn't one.
- **One time for an agent on a session page**: the summary says an agent was active from its first to its last action,
  as Every action lists them, and the reasons give no other time for it. A reason that rests on a working indicator,
  such as Claude in Chrome's, no longer names the times the indicator was visible, which could run past the agent's
  last action.

### Removed

- The release files no longer carry the evaluation code: `agentcake eval` runs from a checkout of the source, which has
  its thresholds and data sets, and an installed AgentCake says so. Nor do they carry the page script's sources or the
  tool that builds it from them, now `tools/build_js.py` in the source (an installation serves the built cake.js, whose
  first line names that tool), or `copy.zh.json`, which nothing read.

### Deprecated

- cake 0.3.x's entry points, `bin/cake` and `cake.py`, and the recorder file that pages set up for cake 0.3.x still
  load, `/rrweb-record.min.js` (`/cake/rrweb-record.min.js` on a server), will be removed in the next release. Use
  `bin/agentcake` or the installed `agentcake` command; the page script has had the recorder inside since 0.4.0.

### Other changes

- [`README.md`](README.md) asks whether some of a site's visits come from AI agents, cites HUMAN Security's figure for
  the growth of traffic from AI agents and agentic browsers, and says that AgentCake can make mistakes. It has a new
  animation and, under it, a row of pictures of the dashboard and the session list that scrolls sideways.
- The name is written AgentCake, one word, everywhere: in the documents, the comments and the first line of the page
  script, whose build id changes with it while its code stays the same.
- Every warning and note on the local pages has the same look: its text in the alert's own colour, with a contrast of
  at least 6.5:1 in both themes. Before, the disk warnings, some warnings in Settings, a session's summary and the
  dashboard's note that a website isn't connected used the main text colour.

## 0.4.2

Web analytics for human and agent sessions on the dashboard, visitors counted across devices when your site says who
signed in, plainer words on every local page, and a fix for a new installation's first page.

### Dashboard

- **Key metrics**: sessions, visitors, page views, active time spent and pages per session, below the Agent sessions
  block.
- **Trends**: one of those five metrics over time, with a line for Human and one for Agent sessions: by hour for
  Today, by day for the last 7 and 30 days, and by month for All time.
- **Paths, Sources, Devices and Geography**: four tables that each show All, Agent or Human sessions, with each row's
  sessions, visitors and page views, and for All the Agent sessions' share. Sources break down by channel, referring
  domain and campaign (UTM) fields, Devices by device type, browser and operating system, and Geography by region,
  country, city, time zone and language. Country, region and city come from a load balancer, so they appear only on a
  server.
- **Top agents** (was Agents that visited) shows the same five metrics for each agent, and every agent is named.
  Unnamed agents share one grey avatar.
- **Reference**, at the bottom, in place of the table of what AgentCake records: the session categories, and which
  visits are counted.
- Until your website sends its own first session, the home page keeps showing how to connect it. Sessions that an
  earlier AgentCake's demo shop recorded don't count.
- **Hover text**: every tooltip and hint on the local pages has the same look, starts each line at the left edge, and
  opens after the pointer rests for 400 ms, or at once on keyboard focus.
- Every dropdown has the same height, and every card title has an icon. The Visitors card's description is two
  sentences, and Top agents and Trends no longer have an information icon beside their metric menus.

### Sessions, visitors and sources

- **Sessions**: a session is one browser tab's activity, and it ends after 30 minutes without activity or after 24
  hours. Each tab keeps its own session, so a human in one tab and an agent in another never share a timeline.
  AgentCake splits uploads from page scripts that don't apply these rules in the same way.
- **Visitors**: the page script keeps a random ID in the browser's local storage, not in a cookie, until a year after
  the visitor's last page view. AgentCake counts visitors by this ID.
- **Signed-in visitors**: call `window.cake.identify(id)` after a visitor signs in and `window.cake.reset()` when they
  sign out. Each signed-in visitor then counts once across browsers and devices, including their visits from before
  they signed in. The browser sends only a one-way hash of the ID with your site key ([`PRIVACY.md`](PRIVACY.md)).
- **Sources**: each page view sends its referring domain (never the full address), its campaign parameters and the
  names of any ad-click parameters (never their values).

### Words and names

- **Plainer words** on every local page and in the reasons for each classification.
- **New names**, the same on the local pages, in the documents and in what the command line prints: "Register and
  continue" (was "Register & Continue"), the server middleware (was the server half), limited evidence (was thin
  evidence), "Install with your AI agent" and "Install manually" (were "Copy this to your AI agent" and "Set up
  manually"), and a session's classification (was its verdict).
- The documents and the local pages' examples name only agents AgentCake can name.

### Detection

- **Extra automation detection**: with this setting on, the rule that notices an automation framework calling your
  site's own document lookups now runs. It never ran before. A visit is judged with the setting as it was when the
  visit was recorded.
- **Impersonated bots**: when a check proves a bot's name false (Googlebot's User-Agent from outside Google's published
  ranges, or a signature that fails verification), the Name layer now reads Agent instead of Bot, as the session's
  classification already did.
- **Agent indicators**: a session whose only mark on the page is an agent's indicator no longer also says that only
  its behavior points to an agent.
- The reason given for a session with too little data no longer says that the minimum number of actions can be
  changed.
- A reason no longer says that a visit has no name when another check names it, such as a verified signature.

### Fixes

- **A new installation's first page**: on its first open, the local page could show "Unable to load AgentCake" until
  it was reloaded. Its first requests each set up the new database at the same time, and one of them found it locked.
  A new database is now set up once per process, and a process waits while another one sets it up.
- **Timeline**: two hand-off labels that are close together take two rows, so they no longer overlap.

### Disk

- **One cleanup rule**: once AgentCake's data reaches 90% of the disk budget, it deletes session replays, oldest first,
  from every kind of session, until the data is under 90% again. Visits and classifications stay. Before, it deleted
  the replays of the oldest human-only sessions once the budget was full.
- When the disk itself runs low (less free space than `disk_min_free_mb`), new replays stop and none is deleted, until
  there is room again.

### Install

- [`INSTALL.md`](INSTALL.md) asks the installing agent to answer in the user's language at its start, not only in its
  last steps.
- `agentcake sentence` prints the English sentence that the local page shows.

### Evaluation and licences

- `agentcake eval` has more labelled agent sessions, 1,118 in all (405 for 0.4.1): more recordings of Claude in Chrome
  and of Codex, more coding agents driving browser tools, libraries that run their own agents, and eight more
  libraries made to look human. The results are in [`eval/README.md`](eval/README.md).
- [`THIRD_PARTY.md`](THIRD_PARTY.md) lists what the web analytics follow: posthog-js's session, visitor ID, source and
  device rules, PostHog's channel rules and web analytics definitions, and the Unicode CLDR region names, whose
  licence ships as `agentcake/data/cldr.LICENSE.txt`.

### Other changes

- [`README.md`](README.md) is rewritten: the problem, the solution, how to install, how AgentCake decides and the size
  of its test data, your data, and connecting a website.
- The bundled lists of names, published IP ranges and signature keys are the ones built for 0.4.1 on 2026-11-14.
  `agentcake lists update` fetches newer ones when you ask.
- A review before this release fixed 15 problems, each with a test. Among them: the links and hover values of the
  dashboard's tables and Trends, active time when uploads arrive out of order, an address that can't be read, the IDs
  of sessions after older ones are deleted, and the page script's start when a session times out as a page opens. The
  review also removed duplicated and unused code, and the evaluation's results are unchanged.

## 0.4.1

Hand-offs found closer to where they happen, a new behavior check, two new environment checks, and the licence texts in
every release file.

### Behavior

- **Fast arrivals.** A pointer that reaches what it clicks at full speed, instead of slowing down into it as a hand
  does, now counts toward Agent. Tools that make the pointer move like a hand often trace their path at an even or
  rising pace; this check reads the whole session's mouse movements before its clicks.
- **Hand-offs at the new actor's first action.** A hand-off is placed at the first action of whoever takes over.
  Steps the model can't tell between the two actors go to the side their own scores make likeliest. The timeline, the
  session's summary and its reasons name the same moment.
- **One meaning of an action.** The Every action list, the hand-offs and the spliced sessions of `agentcake eval` count
  the same actions: the visitor's own click, key or typed input, wheel, and a scroll their input caused. Moving the
  pointer is not an action.
- **Claude in Chrome's indicator tail.** Its working indicator stays on for a few seconds after the agent's last
  action. When the indicator goes off and the visitor acts before another one comes on, its last 4.9 seconds are
  judged on their own evidence instead of given to the agent, so a human who takes over at once is counted as the
  human.
- **A click repeated in place** (inside the square a browser counts as a double-click, the pointer never leaving it)
  shows no approach of its own, so paging through pictures or pressing an arrow again no longer looks like a click
  with no movement before it.
- **Calibration refit** with more Claude in Chrome sessions. The refit changes no verdict, and a session's percent
  moves by 2 points at most.

### Environment

- **Requests that name different operating systems.** A soft rule: in one visit, the page script's requests name
  different operating systems in their User-Agent header. A browser sends the same one with every request; automation
  that changes it can miss some.
- **Apple's system font names on another system.** The page script asks the browser one question: whether it
  recognizes a system font name that only Apple's systems map while it says it runs on another system. Only the
  answer (yes, no or can't tell) leaves the page, never font names or sizes. A soft rule, because a system can alias
  those names, as fontconfig can on Linux. [`PRIVACY.md`](PRIVACY.md) lists it.

### Install and connecting a website

- A coding agent that installs AgentCake or connects a website stops only the programs it started, by the process ID it
  noted, never by port or name, and answers in the user's language ([`INSTALL.md`](INSTALL.md),
  [`AGENTS.md`](AGENTS.md) and `agentcake setup --print --site`).

### Licences

- `agentcake.pyz` carries `LICENSE` and `THIRD_PARTY.md` at its top, as the wheel and the release folder do.
- The bundled lists ship with the licence texts of their sources (PostHog's bot definitions, ai.robots.txt and
  botscent), refreshed with the lists.

### Other changes

- The dashboard's coverage note says a bot is Verified when a signature or the operator's published address range
  confirms it.
- `agentcake eval` writes its report and help in English and checks the thresholds in `eval/thresholds.json`. A5 now
  judges the median hand-off error over the sessions judged Human + agent; a hand-off it did not find counts as over
  the limit.
- [`README.md`](README.md) starts with the problem, then the solution, then the technical details, and calls what
  AgentCake does AI agent traffic analytics.
- The repository is now `tartini-ai/agent-traffic-analytics`. GitHub redirects the old name,
  `tartini-ai/agent-behavior-analysis`.

## 0.4.0

The first release of AgentCake: self-hosted session replay that tells humans from AI agents.

### What it does

- **Every visit judged.** Each session is Human, Agent or Bot. An Agent session is agent only, or human + agent when a
  human and an agent took turns. A session AgentCake can't tell counts as Human and is marked thin evidence.
- **Agents by name.** Claude in Chrome, ChatGPT, Playwright, Selenium and the others, each marked Verified or
  Likely, and Unnamed when AgentCake can't tell which agent it was.
- **Replay and reasons.** Each session plays back with every input masked. A timeline shows who acted when and marks
  each hand-off, and four layers say why: the agent's name, its verification, the browser's environment and the
  behavior.
- **On your computer or a server.** One Python process and one SQLite database, standard library only. On a server,
  only the page script and the collect endpoint are public, and signatures and published IP ranges confirm who an
  agent is.
- **Connected by your coding agent.** One line in your pages loads cake.js. `agentcake setup --print --site` prints the
  steps and the middleware for Next.js, Express, Flask, FastAPI, Django, PHP and WordPress, and `agentcake logs import`
  reads nginx, Apache and Caddy access logs.
- **Private by default.** No telemetry. What visitors type, which keys they press, passwords, card numbers, cookies and
  IP addresses are never recorded. `window.cake.start()` and `window.cake.stop()` follow your site's consent, and
  `agentcake delete --session <id>` removes a visit everywhere.

### Install

Paste the install sentence of [`README.md`](README.md) into a coding agent, or follow [`INSTALL.md`](INSTALL.md) by
hand. Check the download with `shasum -a 256 -c SHA256SUMS`.

### Known limits

An agent that moves and types like a human, with no name and no trace, can pass as a human, and hand-offs are often
found late. [`README.md`](README.md) ("What it can't tell yet") gives this release's numbers, and
[`eval/README.md`](eval/README.md) says how they are measured.
