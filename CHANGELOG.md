# Changelog

Every release of AgentCake, newest first. Each release's files and their `SHA256SUMS` are on
[GitHub Releases](https://github.com/tartini-ai/agent-traffic-analytics/releases).

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
- **Agents by name.** Claude in Chrome, Comet, ChatGPT agent, Playwright, Selenium and the others, each marked
  Verified, Likely or Possible, and Unnamed when AgentCake can't tell which agent it was.
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
