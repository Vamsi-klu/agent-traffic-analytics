# Changelog

Every release of AgentCake, newest first. Each release's files and their `SHA256SUMS` are on
[GitHub Releases](https://github.com/tartini-ai/agent-behavior-analysis/releases).

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
