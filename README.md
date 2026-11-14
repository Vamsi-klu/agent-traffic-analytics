<div align="center">

<img src="docs/assets/readme/crumb.png" alt="AgentCake" width="112">

# AgentCake — AI Agent Behavior Analysis

**Self-hosted session replay that tells humans from AI agents.**

AgentCake helps you detect AI agents visiting your website: it shows which visits were humans, AI agents or bots, and
when a human and an agent took turns. Every session comes with its replay and the reasons for its verdict. It runs on
your own computer or server: one program, one small database, no telemetry.

[![Releases: download](https://img.shields.io/badge/Releases-download-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-behavior-analysis/releases)
[![Issues: report a bug](https://img.shields.io/badge/Issues-report%20a%20bug-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-behavior-analysis/issues)
[![License: MIT](https://img.shields.io/badge/License-MIT-ff5c8a?style=flat)](LICENSE)

**English** · [简体中文](docs/locales/zh-CN/README.md)

</div>

![A walk-through: the dashboard, the session list, then a session where Claude in Chrome hands over to a human](docs/assets/readme/demo.png)

*Recorded on a test shop: Claude in Chrome puts a T-shirt in the cart, then a human takes over and checks out. The
replay jumps to the hand-off, beside the four layers' reasons.*

## Install

Open Claude Code, Codex or another coding agent in a new, empty folder and paste this sentence:

```text
Install AgentCake 0.4.0 for me with curl or the GitHub CLI by following
https://raw.githubusercontent.com/tartini-ai/agent-behavior-analysis/v0.4.0/INSTALL.md
and then tell me which local page to open and how to connect my website.
```

Your agent downloads the release, checks its checksums, installs the `agentcake` command, starts it and runs
`agentcake doctor`. Then open http://127.0.0.1:7878/ in your browser.

- **Requirements:** macOS or Linux, with Python 3.11 or newer, or with uv, which brings its own Python.
- **First open:** register with your e-mail address ([what is sent](#your-data-stays-yours)); the page then walks you
  through connecting your website.
- **By hand:** [`INSTALL.md`](INSTALL.md) has the same steps, one command each.
- **Private preview:** while the repository is private, sign in to the GitHub CLI first (`gh auth login`). Your agent
  then downloads the release with `gh release download v0.4.0 --repo tartini-ai/agent-behavior-analysis`.

## Dashboard

**Humans and AI agents, side by side.**

![The dashboard: agent sessions first, then every visit counted](docs/assets/readme/dashboard.png)

- **Agents first.** Sessions where an AI agent acted for a human lead the page, split into Agent only and Human +
  agent (the two took turns). Each agent is listed by name, such as Claude in Chrome, Comet or Playwright, or as
  Unnamed.
- **Every visit counted.** Human, Agent and Bot each have a count. A session AgentCake can't classify counts as Human,
  tagged Thin evidence, and its reasons say why. Bots are kept, but never shown in the agent charts.
- **What they came for.** How long each kind of session lasts, which agents came, and the pages agents visit most
  beside the pages humans visit most.

## Sessions and replay

**Watch what the agent did, and where control changed hands.**

![A session: the replay, who acted when, and why this verdict](docs/assets/readme/session.png)

- **The replay.** Each session plays back as the visitor saw it, with every input masked.
- **Who acted, when.** A timeline of human, agent and unknown stretches marks each hand-off, and every action is
  listed with who did it.
- **Why this verdict.** Four layers each say what they found: the agent's name, its verification, the browser's
  environment and the behavior.

## How it decides

**Four layers, all on your machine. No AI service is called.**

- **Name and verification.** Names come from the User-Agent and from signed requests, matched against lists that
  ship with each release. On a server, signatures and published IP ranges confirm them.
- **Environment and behavior.** Automation traces, an extension taking over the page, and how the pointer, keys and
  scrolling move.
- **What it recognizes.** Agents that name themselves or sign their requests (ChatGPT agent, Manus, Grok); agents that
  mark the pages they drive (Claude in Chrome, Comet, Browser Use); automation tools, named by the traces they leave
  (Playwright, Puppeteer, Selenium).
- **What it can't tell yet.** An agent that moves and types like a human, with no name and no trace, can pass as a
  human. On held-out data, 17 of 23 Claude in Chrome replays were judged agent, but so was 1 of 39 probably-human
  replays. Only 29.5% of hand-offs are found within 3 seconds ([how it is measured](eval/README.md)).

## Your data stays yours

**No telemetry. What your visitors do stays on your machine.**

- **Nothing sent.** The page script sends visits only to your own AgentCake. AgentCake sends no usage data, and goes
  online only when you ask: to register, to update its lists (`agentcake lists update`) or to check your own site
  (`agentcake doctor`).
- **Never recorded.** What visitors type, which keys they press, passwords, card numbers, cookies and IP addresses.
  If your site asks visitors for consent, it starts and stops recording (`window.cake.start()`, `window.cake.stop()`).
- **Registration, once.** The first time you open the local page, it asks you to register. Your e-mail address, your
  company if you give one, whether you want product updates and which consent text you saw go to Tartini AI only
  when you press "Register & Continue". Collecting visits and the command line work without it.

![Settings, with exactly what registration sent](docs/assets/readme/settings.png)

[`PRIVACY.md`](PRIVACY.md) says what is recorded, where it is kept and how to delete it;
[`docs/privacy-notice-template.md`](docs/privacy-notice-template.md) helps you tell your visitors.

## Connect your website

**One line in your pages, optional middleware on your server.**

After you register, the local page walks you through it in four steps: your website's address, where AgentCake
runs, the page script, and the first visit. Its third step has a sentence for your coding agent, to paste in your
website's code folder. It names your `agentcake` by its full path, and reads like this:

> In this website's code folder, run `agentcake setup --print --site`, follow the steps it prints to connect AgentCake to this website, then run `agentcake doctor` and tell me the result and what is left for me to do.

- **The page script.** One line in your pages loads cake.js (45 KB gzipped). Its checks wait for the page to load and
  run while the browser is idle.
- **The server half.** For Next.js, Express, Flask, FastAPI, Django, PHP and WordPress, the setup also prints
  middleware that tells AgentCake what your server saw of each page request.
- **Local or public.** A site running on this computer sends visits right away. A public website's visitors need
  AgentCake on a server.

## Run it on a server

**For the visitors of a public website.**

- **Same program, server mode.** Only the page script and the collect endpoint are public, on a path of your own
  site. The dashboard stays on the server's 127.0.0.1, behind an SSH tunnel.
- **Docker or systemd.** Run it as a container or as a service.
- **Verification turns on.** On a server, signatures and published IP ranges can confirm who an agent is.

[`SERVER.md`](SERVER.md) has every step.

## Building from source

- **Release files:** `python3 -I tools/release.py build` builds the wheel, `agentcake.pyz`, the release folder and
  `SHA256SUMS` from the commit checked out; `python3 -I tools/release.py --help` says how.
- **With a coding agent:** give it [`AGENTS.md`](AGENTS.md). It says how to run AgentCake from this folder and how to
  change its interface ([`DESIGN.md`](DESIGN.md)).
- **Tests:** `python3 -I -m unittest discover -s tests -v`.
- **Contributing:** [`CONTRIBUTING.md`](CONTRIBUTING.md) says how to run it from source, which checks a pull request
  passes and the rules they keep.

## Feedback

- **Questions:** [`docs/FAQ.md`](docs/FAQ.md) answers the common ones, such as how accurate it is, what Human, Agent
  and Bot mean, and whether it blocks agents.
- **Bugs, wrong verdicts and ideas:** [GitHub Issues](https://github.com/tartini-ai/agent-behavior-analysis/issues).
- **Security vulnerabilities:** please don't open an issue; write to [admin@tartini.ai](mailto:admin@tartini.ai).
  [`SECURITY.md`](SECURITY.md) says what to include and what is in scope.

## License

MIT, copyright Tartini AI: see [`LICENSE`](LICENSE). The third-party code AgentCake bundles (rrweb, BotD, botscent
and the bot lists) keeps its own licenses, listed in [`THIRD_PARTY.md`](THIRD_PARTY.md).

<sub>AgentCake is an independent product and is not affiliated with, endorsed by or sponsored by the makers of the
agents and tools it names. All trademarks belong to their owners.</sub>
