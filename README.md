<div align="center">

<img src="docs/assets/readme/crumb.png" alt="AgentCake" width="112">

# AgentCake — AI Agent Traffic Analytics

[![Releases: download](https://img.shields.io/badge/Releases-download-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-traffic-analytics/releases)
[![Issues: report a bug](https://img.shields.io/badge/Issues-report%20a%20bug-ff5c8a?style=flat)](https://github.com/tartini-ai/agent-traffic-analytics/issues)
[![License: MIT](https://img.shields.io/badge/License-MIT-ff5c8a?style=flat)](LICENSE)

**English** · [简体中文](docs/locales/zh-CN/README.md)

</div>

## The problem

Your website gets plenty of traffic, but the number of buyers stays flat or even declines. Want to understand why? Start
by checking whether humans or AI agents made those visits.

Microsoft Clarity
[analyzed more than 5.2 million sessions involving AI agents](https://clarity.microsoft.com/blog/agentic-analytics-what-agents-do-on-websites/)
over four weeks in 2026. Weekly agent sessions nearly doubled in just three weeks. If your analytics don't recognize
these agents, your daily reports may count their visits as human traffic.

## The solution

We've launched AgentCake, a self-hosted AI agent traffic analytics platform. It records each visit as a session replay.
Our behavioral model and rules then identify whether a human, an AI agent or both drove each session.

Here's what AgentCake can help you understand:

1. **What AI agents found**: See which pages AI agents viewed and whether they found the information they needed. Find
   out whether they only browsed or began signing up.
2. **Where AI agents got stuck**: See the steps where agents stopped. Then decide whether to adapt those steps to make
   your website more agent-friendly.
3. **Which AI agents visit most**: See which agents visit your website most often, such as Claude in Chrome, Grok Bot
   and Muse. Use what you learn to optimize your website for them and increase conversions.

![This animation tours the dashboard and the session list, then replays a hand-off from Claude in Chrome to a human.](docs/assets/readme/demo.png)

*The recording shows Claude in Chrome adding a T-shirt to the cart on a test shop and a human taking over to check out.*

- **Human, AI agent or bot**: AgentCake gives each session a single classification. Agent sessions are
  split into Agent only and Human + agent.
- **Agent names and confidence levels**: AgentCake identifies agents by name, such as Claude in Chrome, ChatGPT and
  Muse, and labels each name Verified or Likely. Agents it can't identify appear as Unnamed.
- **Timeline and reasons**: A timeline shows when a human or an agent was in control during each session and marks
  each hand-off. Next to the replay, you can view the reasons for each classification.
- **Human and agent traffic**: See sessions, visitors, page views and active time for humans and agents. Break down
  the traffic by path, source, device and geography.
- **Self-hosted and open source**: AgentCake runs on your computer or server as a single program. It uses one SQLite
  database and sends no telemetry. The code is available under the MIT License.

## Install

Open Claude Code, Codex or another coding agent in a new, empty folder and paste these instructions:

```text
Install AgentCake 0.4.2 by following the guide at https://raw.githubusercontent.com/tartini-ai/agent-traffic-analytics/v0.4.2/INSTALL.md step by step.
Use curl or the GitHub CLI to download the guide.
Finally, print the address of the AgentCake local page and the steps to connect a website.
```

Your agent downloads the release and verifies it. The agent then starts AgentCake and runs `agentcake doctor`, which
checks that the installation works.

Next, open http://127.0.0.1:7878/ and register your installation. The page guides you through connecting your website.

AgentCake runs on macOS and Linux and requires uv or Python 3.11 or later. To install manually, follow the steps in
[`INSTALL.md`](INSTALL.md). While the repository is private, sign in to the GitHub CLI first (`gh auth login`).
Your agent then downloads the release with `gh release download v0.4.2 --repo tartini-ai/agent-traffic-analytics`.

## How it decides

To identify agent sessions and the agents behind them, AgentCake checks four layers of evidence on your machine.

- **Name**: AgentCake matches the name in the User-Agent string against the agent lists included in each release.
- **Verification**: On a server, AgentCake verifies self-reported agent names with request signatures and published IP
  ranges.
- **Environment**: AgentCake detects automation traces, spoofed browsers and the page markers that some agents add.
- **Behavior**: Our behavioral model analyzes pointer movement, keyboard timing and scrolling for every action in a
  session.

The behavioral model scores each action. It looks for two independent kinds of evidence, such as pointer movement and
typing, before it classifies a session as agent traffic.

AgentCake's test data includes 1,118 agent sessions from our own recordings and 7,122 human sessions. Most of the human
sessions come from nine public data sets. Five of these data sets were never used to build or tune AgentCake.

For details on how each number is counted, see the [evaluation report](eval/README.md).

## Your data stays yours

The page script sends visit data only to your own AgentCake installation. The installation doesn't send any usage data.
AgentCake accesses the internet only when you register, update its agent lists or run a site check.

AgentCake doesn't record what visitors type or which keys they press. It also doesn't record passwords, card numbers,
cookies or IP addresses.

To count visitors, AgentCake stores a random ID in each visitor's browser without using a cookie. The ID expires a year
after the visitor's last visit. AgentCake keeps only the domain of the referring page.

AgentCake sends your registration details only once, when you select **Register and continue**. AgentCake records visits
whether or not you register.

For details about how AgentCake handles data, see [`PRIVACY.md`](PRIVACY.md). To inform your visitors, you can use
the template in [`docs/privacy-notice-template.md`](docs/privacy-notice-template.md).

## Connect your website

After you register, copy the setup instructions from the local page. Open a coding agent in your website's project
folder, and paste the instructions. The agent asks for your website's address and the machine that will run AgentCake.

To load cake.js on every page, the agent adds one line of code to your shared page layout. The cake.js script is 48 KB
gzipped. The agent can also add server middleware for Next.js, Express, Flask, FastAPI, Django, PHP and WordPress.

You can also complete these steps manually.

For a public website, run AgentCake on a server with Docker or systemd. Open the dashboard through an SSH tunnel to keep
it private. For step-by-step instructions, see [`SERVER.md`](SERVER.md).

## Help and contributing

For answers to common questions, see [`docs/FAQ.md`](docs/FAQ.md). If AgentCake misclassifies a session or doesn't
recognize an agent, open an [issue](https://github.com/tartini-ai/agent-traffic-analytics/issues/new?template=wrong_verdict.yml).
Describe what happened without including any visitor data.

The rules and the model's parameters are JSON files in `agentcake/data/`. When you send a pull request, include the
`agentcake eval` results from before and after your change. A pull request is merged only if it does not increase the
number of humans classified as agents.

For contribution guidelines, see [`CONTRIBUTING.md`](CONTRIBUTING.md). For coding agent instructions, see
[`AGENTS.md`](AGENTS.md).

To report a security vulnerability, email [admin@tartini.ai](mailto:admin@tartini.ai) instead of opening an issue. For
more information, see [`SECURITY.md`](SECURITY.md).

## License

AgentCake is released under the MIT License, copyright Tartini AI. For the full license, see [`LICENSE`](LICENSE).

Third-party components bundled with AgentCake retain their respective licenses. For the list, see
[`THIRD_PARTY.md`](THIRD_PARTY.md).

<sub>AgentCake is an independent product and isn't affiliated with the developers of the agents and tools it names.
Those developers don't endorse or sponsor AgentCake. All trademarks belong to their owners.</sub>
