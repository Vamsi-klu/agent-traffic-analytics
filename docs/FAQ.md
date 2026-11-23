# Questions about AgentCake

Short answers, with links to the documents that give the details.

## How do I detect AI agents visiting my website?

Add AgentCake's page script to your pages and run AgentCake on your computer or on a server your site can reach. Each
visit that runs the script is then classified as Human, Agent, or Script bot. You can watch replays and see the reasons
for each classification. Names come from the User-Agent and from signed requests; traces in the browser and the way the
pointer, keys and scrolling move cover agents that don't name themselves.

To set it up, paste the instructions from the [README](../README.md#install) into a coding agent. The agent installs
AgentCake and connects your website. If AgentCake is already installed, copy the instructions for your agent from the
**Connect your website** page.

## Can AgentCake detect Claude in Chrome?

Yes, while it marks the page it drives. Claude in Chrome draws its own marks on the page while it acts, such as its
"Claude is working here" tag and its Stop button, and older versions left elements and styles in the page; the page
script notices them. In our tests it recognized 153 of 170 Claude in Chrome
sessions; the 17 it missed are PostHog replays, which hold only its behavior, and lab recordings with no actions
([how it is measured](../eval/README.md)).

## Which agents and automation tools does it recognize?

- **Agents that name themselves or sign their requests:** ChatGPT, Manus, Grok.
- **Agents that mark the pages they drive:** Claude in Chrome.
- **Automation tools:** Playwright, Puppeteer, Selenium.

Each is named with how sure AgentCake is: Verified (a signature or a published IP range) or Likely (the name it gives,
or its own traces). An agent AgentCake can't name is listed as Unnamed.

## How does it tell humans from AI agents?

Four layers, all on your machine: the agent's name (User-Agent, signed requests), its verification (on a server:
signatures and published IP ranges), the browser's environment (automation traces, an extension taking over
the page) and the behavior (how the pointer, keys and scrolling move). The lists of names and IP ranges are included
with each release. AgentCake downloads newer lists once a month, or when you run `agentcake lists update`.

## How accurate is it?

We tested it on 14 data sets from about 350 websites. It recognized 1,025 of 1,118 agent sessions from 37 tools, and
mistook 2 of 7,122 sessions by at least 400 real people for an agent. Where a human and an agent took turns, it judged
106 of 159 sessions Human + agent and put the hand-off a median of 0 seconds from the real one. An agent that moves and
types like a human, with no name and no trace, can pass as a human. [`eval/README.md`](../eval/README.md) says how each
number is counted and where it falls short.

## What do Human, Agent, and Script bot mean?

- **Human:** A human acting alone. The behavior model isn't used on a phone or tablet: such a visit counts as Human
  when its screen and touch support match the device and the other layers find nothing. A session AgentCake can't tell
  (too few actions, a phone or tablet it can't confirm, or evidence too weak or pointing both ways) also counts as
  Human and is marked limited evidence, with the reason. For such a session whose browser reports a phone or
  tablet that AgentCake can't confirm, the reasons say which checks failed, such as touch points or the screen size.
- **Agent:** An AI agent or an automation tool. Agent only means it acted from start to finish; human + agent means a
  human and an agent took turns, and the timeline marks each hand-off.
- **Script bot:** A program on the bot list that ran the page script, such as a search engine, a monitor, or a link
  preview. Their sessions are recorded and counted but excluded from agent charts.

AgentCake only counts visits that run the page script, so crawlers and bots that don't run JavaScript aren't recorded.

## Does it block AI agents?

No. AgentCake records and explains; it never blocks or challenges a visitor, and your site works the same with it.

## How is this different from replaying my own AI agent's runs?

Tools that replay your own agent show what your agent did in its browser. AgentCake works the other way round: it
records the visitors of your website and tells you which of them were AI agents, and when a human and an agent took
turns.

## How is it different from web analytics and bot protection?

Web analytics count visitors, and many leave out traffic they take for automated. Bot protection decides whether to
block a request. AgentCake records each visit that runs its page script and classifies it as Human, Agent, or Script
bot, with the reasons for each classification.

## Does it send my visitors' data anywhere?

No. The page script sends visits only to your own AgentCake, and AgentCake sends no telemetry. AgentCake uses the
internet only to register once, to run site and server checks, and to download its lists. On a server, AgentCake also
downloads the city database. By default, AgentCake downloads these files once a month. You can turn this off in
Settings. What visitors type, which keys they press,
passwords, card numbers, cookies and IP addresses are never recorded. To count visitors, the page script keeps a
random ID in each visitor's browser, which expires a year after their last visit ([`PRIVACY.md`](../PRIVACY.md)).

## Does a visitor who uses two devices count twice?

Yes, unless your site tells AgentCake when they sign in. Call `window.cake.identify(user.id)` after a visitor signs in,
with an internal ID that is hard to guess (not an e-mail address or a number that counts up), and
`window.cake.reset()` when they sign out. Each visitor who signs in then counts once across browsers and devices, their
visits before signing in included. The browser sends only a one-way hash of the ID with your site key, never the ID.
Your site key is public, so the hash is a pseudonym, not anonymous data ([`PRIVACY.md`](../PRIVACY.md#counting-a-signed-in-visitor-once)).

## Does it call an AI service to decide?

No. AgentCake classifies every session on your computer or server. Each classification is based on AgentCake's lists
and on what the page script and your web server report.

## Can I run it on a server for a public website?

Yes. You can run AgentCake on your own server with Docker Compose or systemd. By default, your pages load the page
script from a subdomain of your site, such as `cake.example.com`. If your site already has a load balancer or a reverse
proxy, you can use a path of your own site instead. Only the page script and the collect endpoint are public. The
dashboard is available only at 127.0.0.1 on the server. To open it from your computer, use an SSH tunnel. For details,
see [`SERVER.md`](../SERVER.md).

## Is it free and open source?

Yes, under the MIT licence ([`LICENSE`](../LICENSE)). The third-party code it bundles keeps its own licences
([`THIRD_PARTY.md`](../THIRD_PARTY.md)).
