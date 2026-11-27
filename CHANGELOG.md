# Changelog

Every release of AgentCake, newest first. Each release's files and their `SHA256SUMS` are on
[GitHub Releases](https://github.com/tartini-ai/agent-traffic-analytics/releases).

## 0.6.3 (unreleased)

A Muse or Grok Bot session is now shown as Human + agent only when its timeline shows the agent acting and a
hand-off.

### Upgrading from 0.6.2

- To upgrade a server, follow "Upgrading" in [`SERVER.md`](SERVER.md#upgrading). On a computer, give your coding agent
  the instructions in [`README.md`](README.md) again. It asks you before it stops the running version. Your site key
  and your data stay the same.
- `deploy/cake.service`, `deploy/Caddyfile`, `docker-compose.yml`, `Dockerfile` and the database's format are the
  same as in 0.6.2.
- After the upgrade, AgentCake classifies the sessions it already has again with the new rules. A session is
  classified again when you open it, and the others in the background, newest first. A session whose replay was
  removed to free space keeps its 0.6.2 classification.

### Detection

- A session of Muse or Grok Bot, which drive their own cloud browser, is no longer shown as Human + agent unless its
  timeline shows the agent acting and a hand-off: human-looking actions there count as the agent's. A takeover the
  timeline shows, where the agent acts and then a human takes over its live view, is still Human + agent. The
  session's reasons say why.

## 0.6.2

A session is now one browser's visit across all of its tabs, and a human who scrolls or hovers beside their work, or
whose page clicks by itself, is no longer shown as Human + agent.

### Upgrading from 0.6.1

- To upgrade a server, follow "Upgrading" in [`SERVER.md`](SERVER.md#upgrading). On a computer, give your coding agent
  the instructions in [`README.md`](README.md) again. It asks you before it stops the running version. Your site key
  and your data stay the same.
- `deploy/cake.service`, `deploy/Caddyfile`, `docker-compose.yml` and `Dockerfile` are the same as in 0.6.1. AgentCake
  adds a table and three columns to the database when it first opens it.
- After it starts, AgentCake joins the tabs of the sessions it already has into sessions across tabs, in the
  background. First it copies `cake.db` to `backups/`, which needs free disk of 1.1 times the database's size. New
  uploads wait while it copies, and none is lost. Until the joining is done, the dashboard counts each older tab as a
  session of its own. After it, there are fewer sessions, more pages per session and longer active time; visitors and
  page views stay the same. The copy stays in `backups/` until you delete it.
- AgentCake also classifies the sessions it already has again with the new rules. A session is classified again when
  you open it, and the others in the background, newest first. A session whose replay was removed to free space
  keeps its 0.6.1 classification.
- A tab that is open while your site starts serving the new page script begins a new session at its next page.

### Sessions across tabs

- A session is one browser's visit to your site, across all of its tabs. A new one starts once no tab has had
  activity for 30 minutes, or after 24 hours. Until now, each tab was a session of its own.
- The page script keeps the session's id in `localStorage`, which every tab of your site shares, and an id for each
  tab in `sessionStorage`. A duplicated tab, or a window your site opens with `window.open`, gets an id of its own.
  Where `localStorage` takes no writes, each tab is a session of its own; where no storage can be used, each page.
  When `window.cake.stop()` removes the ids in one tab, no other tab writes them back.
- AgentCake joins the tabs of a script that sends no session id, such as an older page script, by its visitor id,
  with the same rules.
- Each tab is still classified on its own. A session is an Agent session when an agent acted in any tab, and Human +
  agent when a human with enough actions acted in another tab too, or one tab was Human + agent. A tab with too few
  actions doesn't count next to a tab with enough. A session is a Script bot only when every tab is one.
- The session list has one row per session, with how many tabs it had and a line for each tab. On the session page,
  the replay follows the visitor from tab to tab, or shows the tab you pick. The timeline has a track for each tab and
  marks the hand-offs between tabs. Pages visited, Server middleware and All actions have a Tab column, and the
  reasons are shown for each tab.
- On the dashboard, Sessions counts sessions and Pages per session counts the pages of all their tabs. Active time is
  the time any tab of the session was shown: a moment two tabs were shown counts once. The source and the entry page
  are the first tab's.
- The old address of a tab opens the session it is part of now.
- `agentcake delete --session <id>` deletes the whole session, given the id of any of its tabs or the session's id. A
  retention of 30 or 90 days deletes whole sessions.
- New command: `agentcake session-counts [--db <file>]` counts a database's sessions both ways, one per tab and across
  tabs. It opens the database read-only and prints only counts, so you can see how your numbers will change before
  you upgrade a server.

### Detection

- A human is no longer shown as Human + agent for scrolling or hovering over a browser window that isn't active, for
  moving that window, or for a page's own scripts that click, such as an autoplaying carousel:
  - Acting while the page has no focus counts only clicks, key presses and typing. An agent that clicks or types into
    a window without focus still counts.
  - The movements a browser reports while a page scrolls under a pointer at rest don't count as movements without
    motion. A change in where the page sits on the screen doesn't count when the window moved by as much, when the
    next movement keeps it, or when it is 2 pixels or less. A click made with the keyboard is not a press.
  - Events a script sends count as automation only when they imitate a device: a pointer, a key, a wheel or a touch.
    A script's clicks and inputs, which sites send to drive their own widgets, don't, and behavior is read from the
    visitor's own input only.
  - Human + agent decided from behavior alone needs at least 3 clicks or inputs from the agent itself. Otherwise the
    session is Human, and its reasons show the agent's part as too short.
- When a name, a signature or a trace makes a session Human + agent but the agent took no action of its own, the
  title says "A human, with <agent> in the browser", and the agent's share of the actions is 0%.
- In our tests, AgentCake recognized 1,020 of 1,118 agent sessions (1,025 in 0.6.1) and judged 81 of 159 sessions with
  a hand-off Human + agent (106 in 0.6.1). It still judged 2 of 7,122 human sessions agents. See
  [`eval/README.md`](eval/README.md).

### Local page

- The pages open in the Minimal style unless this browser picked a style before. A browser that picked Cake keeps it.

### Install guide

- `INSTALL.md` asks the site owner about an install of a command-line tool as an item of its own, and doesn't ask
  about defaults the guide doesn't ask about. The agent's proposal names a domain as the other choice to an sslip.io
  name, with its risks. When the site owner approves only part of it, the agent does only that part and lists what is
  left. Its last message says that, after registering, the local page shows how to connect the website.

### Fixes

- `agentcake migrate` removes a backup copy that fails its check, instead of leaving it in `backups/`.
- A window geometry record whose values aren't numbers no longer keeps a session from being classified.

### Page script

- `cake.js` is 151 KiB minified, 49 KiB gzipped (148 KiB and 48 KiB in 0.6.1).

## 0.6.1

A visit from a real phone or tablet, with nothing else found, now counts as Human without the Limited evidence
tag.

### Upgrading from 0.6.0

- To upgrade a server, follow "Upgrading" in [`SERVER.md`](SERVER.md#upgrading). On a computer, give your coding agent
  the instructions in [`README.md`](README.md) again. It asks you before it stops the running version. Your site key
  and your data stay the same.
- `deploy/cake.service`, `deploy/Caddyfile`, `docker-compose.yml`, `Dockerfile` and the database's format are the
  same as in 0.6.0.
- After the upgrade, AgentCake classifies the sessions it already has again with the new rules. A session is
  classified again when you open it. The others are classified again in the background, newest first, up to 50 every
  30 seconds. The dashboard's counts change as this goes on.
- A session whose replay was removed to free space keeps its 0.6.0 classification. If it's a phone or tablet session
  shown as Human, it no longer shows a percent.

### Detection

- The behavior model isn't used on phones and tablets. A phone or tablet visit now counts as Human, without the
  Limited evidence tag, when all of these are true:
  - At least one page recorded the browser's details. On every page that did, the browser says it's a phone or
    tablet, reports touch points, and has a screen the size of the device that the User-Agent names.
  - The name and verification layers found nothing. The environment layer found only weak signals, which are for
    information only.
  - No rule names the browser the page is open in, such as Cursor's in-app browser, and no agent product's indicator
    appeared on a page.
- To check the device, AgentCake also recognizes these real devices:
  - Chrome on an Android tablet that shows the desktop site, which is its default there. Its User-Agent names no
    device.
  - A Pixel Tablet, whose User-Agent the Devices table reads as a phone's.
  - An iPad or iPhone that shows the desktop site. Its User-Agent names a Mac, so AgentCake reads the device from a
    web worker. If a page closed before its own web worker reported, AgentCake uses the device that the web workers
    of the visit's other pages reported, if they all reported the same iPad, iPhone, or iPod.
- Other phone or tablet visits that aren't an Agent or a Script bot still count as Human with the Limited evidence
  tag. When the device didn't pass the check, the behavior layer's reasons say which part failed: the browser reports
  a phone or tablet on some pages but not on others, a page reports no touch points or no valid screen size, the
  screen is too large or too small for the device type, the User-Agent names no phone or tablet, or no web worker
  reported the device of an iPad or iPhone that shows the desktop site.
- The behavior layer's first reason for a phone or tablet now reads "The browser reports a phone or tablet, so the
  behavior model isn't used."
- A phone or tablet session shown as Human doesn't show a percent, with or without the Limited evidence tag. An Agent
  or a Script bot on a phone keeps its percent.
- On phones and tablets, AgentCake no longer reads the weak signal "The visible page area became shorter." A mobile
  browser's address bar changes the page's height in the same way when it hides and appears.
- The Limited evidence count under Human on the dashboard and the Limited evidence filter of the session list follow
  the new rules.

### Local API

- `/api/session` gives `percent` as `null` for a phone or tablet session shown as Human.

## 0.6.0

You can have a coding agent set up AgentCake for your website after you approve its plan. On a server, AgentCake runs at
a subdomain of your site by default. AgentCake also downloads the latest agent lists every month.

### Upgrading from 0.5.1

- To upgrade a server, see "Upgrading from 0.5.1" in [`SERVER.md`](SERVER.md#upgrading-from-051). Your site key stays
  the same. The dashboard keeps all existing data.
- By default, AgentCake downloads updates from the internet every month. To stop these downloads, turn off **Automatic
  updates** in **Settings**.
- AgentCake no longer reads location headers from a load balancer. You can remove `X-Cake-Region`, `X-Cake-Subdivision`,
  and `X-Cake-City` from your load balancer's settings. Sessions recorded earlier keep their location data.
- For Next.js, Express, and Hono, copy the server middleware into an `agentcake-edge` folder in your repository. Vercel
  and other CI services can then install the middleware. To get the steps, run `agentcake setup --print --site`.

### Install with a coding agent

- Use the instructions in [`README.md`](README.md) to install AgentCake on your computer or a server. Paste them into a
  coding agent in your website's code folder. For a site builder, use a new, empty folder.
- The agent follows the guide in [`INSTALL.md`](INSTALL.md). The agent reviews your website's code, hosting, and DNS
  without changing any files. Answer the agent's questions about your website, such as its address.
- The agent will prompt you to approve its plan before it installs AgentCake. Each plan lists the setup, your tasks,
  the monthly cost of each item, and the total cost.
- The agent can also do these tasks:
  - Create a server
  - Add a DNS record
  - Deploy your website
  - Paste the script tag in a site builder
  - Check the setup with `agentcake doctor`
- These tasks might require you to sign in to your accounts, enter payment details, and accept terms.
- If AgentCake is already installed, copy the instructions for your agent from the **Connect your website** page.
- AgentCake recognizes a folder with only a WordPress theme or plugin as a WordPress site. The setup steps for this
  folder use AgentCake's WordPress plugin.

### Install on a server

- By default, your website's pages load the page script from a subdomain, such as `cake.example.com`. To start AgentCake
  and Caddy, run `docker compose up -d` in the release folder on the server.
- Caddy automatically obtains and renews the HTTPS certificate for your subdomain. Caddy forwards only requests for
  `/cake/cake.js` and `/cake/collect` to AgentCake. For details, see [`SERVER.md`](SERVER.md).
- If your site has its own load balancer or reverse proxy, you can use a path of your site instead. With either option,
  the dashboard is available only at 127.0.0.1 on the server.
- Use the new `public_url` setting for the address where browsers reach AgentCake on a subdomain. For details, see
  "Settings" in [`SERVER.md`](SERVER.md#settings).
- With the new `proxy_hops` setting, AgentCake can read the visitor's IP address from `X-Forwarded-For` on the path
  option. By default, the value is 0, and AgentCake reads `X-Cake-Client-IP` as before.
- On the public listener, `/cake/collect` supports CORS, so pages on your website can send data to your subdomain. No
  cookies are sent or requested.
- The setup page shows the commands and the DNS record that a subdomain needs. To get the script tag for your subdomain,
  set `public_url` and run `agentcake setup --print --site`.
- To use CloudFront with the path option, follow the steps in [`SERVER.md`](SERVER.md#path-rules). Requests from
  CloudFront to the server use plain HTTP on port 8080 and travel over the internet.
- If your site doesn't have its own domain, you can use a free sslip.io name for AgentCake's server. To learn about the
  risks, see "Sites without their own domain" in [`SERVER.md`](SERVER.md#sites-without-their-own-domain).
- To compare hosting platforms and their requirements, see [`docs/hosting.md`](docs/hosting.md). It shows which setups
  are free and the approximate monthly cost of the others.
- With Docker Compose, you can back up the `agentcake-data` volume with the commands in "Backups" in
  [`SERVER.md`](SERVER.md#backups).

### `agentcake doctor`

- For a subdomain, doctor checks each step that a visitor's browser takes to reach AgentCake. Doctor's test upload
  doesn't count as a visit. For the path option, doctor runs three of these checks:
  - **Self-check upload**
  - **Visitor IP address**
  - **Recent visitor IP addresses**
- When a header is removed or replaced, doctor can identify the CDN or proxy that AgentCake runs behind. For some
  platforms, doctor also shows the setting to change.
- The self-check upload can fail with a 403 error from CloudFront. To fix it, check that the `/cake/*` behavior forwards
  requests to AgentCake and allows POST. Doctor shows which **Allowed HTTP methods** to choose.
- Doctor shows a warning instead of a failure in these cases:
  - Proxied DNS records on Cloudflare
  - Cached pages without the token
  - Uncached pages that time out
- On a server, doctor shows a warning when the city database is missing or old. The warning says when AgentCake
  downloads the database, or shows the command that downloads it.
- For Next.js, Express, and Hono, doctor checks the `agentcake-edge` folder. For each problem, doctor shows how to fix
  it.
- For a folder with only a WordPress theme or plugin, doctor skips the code checks. To check the plugin, set `site_url`
  to a page of your WordPress site.
- When `agentcake doctor --url` can't verify a site's HTTPS certificate, it says why. For example, the certificate has
  expired, is self-signed, or is for another host name.
- When the certificate's issuer isn't trusted, doctor also lists possible causes, such as a proxy that replaces
  certificates. Doctor no longer blames a sandbox for certificate errors.

### Location

- When an upload arrives, AgentCake looks up the visitor's country, region, and city in the server's city database.
  Sessions recorded while the server has no city database show Not set as their country.
- The city database is DB-IP's IP to City Lite, under the CC BY 4.0 license. AgentCake doesn't store the visitor's IP
  address or send any data about it outside your server.
- By default, AgentCake downloads a missing database 1 to 15 minutes after it starts. It does this only on a server that
  reads visitors' IP addresses. To see the database in use, run `agentcake lists`.
- In **Geography**, the Region and City tables are grouped by country. Sessions without a known region or city appear in
  one row per country, such as "Germany – Not set".
- While the database is in use, the dashboard and the session page show "IP Geolocation by DB-IP" with a link to DB-IP.
  The database's license requires this credit.

### Automatic updates

- Once a month, `agentcake serve` downloads the latest agent lists and IP ranges. On a server that reads visitors' IP
  addresses, AgentCake also downloads the city database. You can also run `agentcake lists update`.
- The updates connect only to public addresses that are listed in AgentCake's data files. The updates don't send any
  data about your site, its visitors, or your installation. For details, see [`PRIVACY.md`](PRIVACY.md).
- In **Settings**, use the **Automatic updates** switch to turn the updates on or off. By default, the switch is on,
  both on your computer and on a server. The setting is `lists_auto_update`.
- If you turn off **Automatic updates** while the lists download, AgentCake skips the city database. When a download
  fails, AgentCake keeps the lists or database in use and tries again the next day.
- Settings shows when the last update ran and whether it succeeded. Doctor and `/api/health` also show the last update.
  AgentCake records the updates in `updates.json` in the data folder.
- Updates run at the lowest CPU priority on every server, with Docker Compose or systemd. On a server with 1 vCPU,
  Docker reports AgentCake as healthy during the first update.
- The Docker health check has a timeout of 30 seconds.
- With systemd, AgentCake keeps running if an update exceeds the memory limit. **Settings** and `agentcake doctor` show
  the failed update. To install the new `deploy/cake.service`, follow the steps in [`SERVER.md`](SERVER.md#upgrading).

### Detection

- With CloudFront's default settings, the session page lists the missing `Accept-Language` header only as a weak signal.
  This also applies to other proxies that change the `User-Agent` header or remove `Sec-Fetch-Mode`.
- AgentCake can now verify signed agents behind a proxy that changes the `Host` header. AgentCake also checks the
  signature against `site_domain` and the host in `public_url`.
- If most recent sessions with an IP address come from a CDN, AgentCake might read the CDN's address. The dashboard
  shows a warning, and sessions that end during this time are classified without IP addresses.
- On a server, AgentCake ignores the order of request headers, because a proxy or CDN might change it.
- AgentCake stores the `Host` header of each upload, which contains your site's name or AgentCake's name. Doctor uses
  this header to check that its test upload arrives unchanged. For details, see [`PRIVACY.md`](PRIVACY.md).
- AgentCake checks whether a phone or tablet user agent matches the browser. Device emulation in developer tools can
  cause the same mismatches. These mismatches alone don't classify a session as Agent.
- In desktop mode, an iPad page reports a Mac, while its web worker reports an iPad. On a touch screen, AgentCake
  doesn't treat this as a mismatch.
- The bundled lists date from November 19, 2026, and include these changes:
  - CloudFront ranges marked as CDN
  - More PerplexityBot and Claude-Agent ranges
  - Updated iCloud Private Relay ranges
  - Updated AWS ranges

### Dashboard

- **Script bot** is the new name of the **Bot** classification. AgentCake records only bots that run the page script.
  This count differs from the bot traffic in other analytics tools.
- Counts on the dashboard and in Session replay use a thousands separator, such as 1,900. The API returns numbers
  without a separator.
- The local pages have two styles: **Cake**, which is the default, and **Minimal**, a plain style for reports and
  screenshots. To switch, use the **Style** menu in the top bar. Your browser saves your selection.
- The local pages always use a light theme.
- The behavior model doesn't classify phone or tablet visits. If such a visit is classified as Human with limited
  evidence, its session page has the title "Phone or tablet visit".

### Local API

- Both `/api/health` and `/api/overview` return a new `address_check` field. It shows how many recent sessions with an
  IP address came from a CDN. It also indicates whether AgentCake might be reading a CDN's IP address.
- The new `places` field in `/api/health` shows the city database in use. The new `updates` field shows the status of
  automatic updates. `/api/settings` also includes `lists_auto_update` and the result of the last update.
- In `/api/web`, the `place` field shows where Geography gets its location data. When AgentCake uses the city database,
  the `attribution` field in `/api/session` contains DB-IP's credit.
- The new `server` field in `/api/setup` contains the server setup that the setup page shows.
- The API continues to use `bot` in field names and values for Script bot sessions.

### Fixes

- AgentCake compresses the page script, cake.js, with gzip for browsers that support it. This reduces the download from
  148 KB to 48 KB. AgentCake also sends an ETag for the script.
- You don't need to restart AgentCake after `agentcake lists update`. This also applies to the keys that verify Web Bot
  Auth signatures.
- When a download is shorter than its `Content-Length` header, AgentCake tries the download again. If every attempt
  fails, AgentCake keeps using the current lists.
- AgentCake rejects these POST requests on both listeners. It returns an error and closes the connection without reading
  the body:
  - No `Content-Length` header
  - Two `Content-Length` headers
  - A negative or non-numeric length
  - A length above the limit
  - A `Transfer-Encoding` header
- To clear the `site_dir` setting, run `agentcake config set site_dir ""`. This command doesn't set `site_dir` to the
  current folder.
- The WordPress plugin's signatures work on PHP without `getallheaders()`. On the Plugins page, WordPress shows the
  plugin's version as 0.6.0.

### Removed

- To run AgentCake, use `bin/agentcake` or the installed `agentcake` command. The release doesn't include `bin/cake` or
  `cake.py` from 0.3.x. If your systemd service runs `cake.py`, install `deploy/cake.service` again.
- If a page still loads `/rrweb-record.min.js` or `/cake/rrweb-record.min.js`, remove that script tag. This recorder
  file from 0.3.x is no longer available. The page script includes the session recorder.
- For more about these changes, see "Upgrading" in [`SERVER.md`](SERVER.md#upgrading).

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
