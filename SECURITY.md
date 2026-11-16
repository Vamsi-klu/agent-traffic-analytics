# Security policy

## Supported versions

Security fixes go into the latest release only. Before you report, check that the problem is still there in the latest
release, and say which version you run (`agentcake --version`).

## Reporting a vulnerability

Please don't open a public issue. Write to [admin@tartini.ai](mailto:admin@tartini.ai) with:

- **The version** and how AgentCake runs: on your computer, or on a server with Docker or systemd.
- **What an attacker can do**, and the steps or a proof of concept that shows it.
- **No real visitors' data.** Leave out replays, IP addresses, e-mail addresses and site keys; if your report needs
  them, say so first and we'll agree how to send them.

We reply to every report, and fix what we confirm in a new release whose notes credit you, unless you'd rather not be
named.

## What is in scope

- **The public half on a server:** the page script and the collect endpoint under your site's path
  ([`SERVER.md`](SERVER.md), "What the public listener answers").
- **The local page:** the dashboard, sessions, replay, settings and their JSON API, which listen on 127.0.0.1 only.
- **What it promises not to keep:** anything [`PRIVACY.md`](PRIVACY.md) says is never recorded (what visitors type,
  passwords, card numbers, cookies, IP addresses) that ends up in the data folder anyway.
- **The site middleware and the install:** the middleware `agentcake setup --print --site` prints, the release files and
  their checksums, and the steps of [`INSTALL.md`](INSTALL.md).

## What is not a vulnerability

- **An agent judged human.** An agent that moves and types like a human, with no name and no trace, can pass as a human
  ([`docs/FAQ.md`](docs/FAQ.md), "How accurate is it?"). Report it as a wrong classification in an issue instead.
- **Anyone who can log in to the server can open the dashboard.** It has no login on purpose: it listens on 127.0.0.1
  only, and you reach it through an SSH tunnel ([`SERVER.md`](SERVER.md)).
- **Made-up visits sent to the collect endpoint.** Like any analytics script's endpoint, it takes what browsers send
  it, within the limits [`SERVER.md`](SERVER.md) lists.
