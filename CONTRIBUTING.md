# Contributing to AgentCake

Thank you for helping. Bugs, wrong verdicts and ideas go to
[GitHub Issues](https://github.com/tartini-ai/agent-behavior-analysis/issues); security vulnerabilities go to
[`SECURITY.md`](SECURITY.md), not to an issue.

## Before you start

- **Open an issue first** for anything larger than a small fix, so that we agree on it before you write it.
- **AgentCake stays small.** One Python process, one SQLite database, the standard library only at run time, and no
  telemetry. A change that needs a dependency or a network call while AgentCake runs won't be merged.
- **A wrong verdict is worth a report on its own.** Say which agent or browser it was and what the session page's
  reasons said; that helps more than a guess at the rule to change.

## Run it from source

You need Python 3.11 or newer and Node 24 (`web/.nvmrc`). Build the local pages once, then start this checkout:

```sh
cd web
npm ci
npm run build
cd ..
bin/agentcake start
```

Then open http://127.0.0.1:7878/. [`AGENTS.md`](AGENTS.md) says the same for a coding agent.

## Where things are

- [`agentcake/`](agentcake/): the program: command line, server, the four detection layers (`detect/`), the page script.
- [`web/`](web/): the local pages (React, shadcn/ui, the Frosting theme), built into files that `agentcake` serves.
- [`edge/`](edge/): the optional middleware for your website's server: Node, PHP, Python and WordPress.
- [`bin/`](bin/): the `agentcake` command.
- [`docs/`](docs/): the FAQ, the upload format, web server examples, README's pictures and its translations.
- [`deploy/`](deploy/): the systemd service for a Linux server ([`SERVER.md`](SERVER.md)).
- [`eval/`](eval/): how README's accuracy figures are measured.
- [`tests/`](tests/): the tests, one `test_<module>.py` per module, with their fixtures and the browser tests.
- [`tools/`](tools/): the checks below, the release build and the scripts that build the bundled lists.
- [`.github/`](.github/): the issue forms, the pull request template and the release workflow.

## Tests and checks

A pull request passes the same tests and checks as a release. From the repository's root:

```sh
python3 -I -m unittest discover -s tests -v
python3 tools/check_hardcode.py
python3 tools/check_imports.py
python3 tools/check_imports.py tools
python3 tools/check_size.py
```

Each check reports 0. The browser tests run when `CAKE_PLAYWRIGHT` names `web/node_modules/playwright-core`, and say
why they are skipped otherwise. For a change to the local pages, also run, in `web/`:

```sh
npm ci
npm run check:ui
npm run build
npm run visual
```

## Rules the checks keep

- **Standard library only** at run time (`tools/check_imports.py`).
- **Nothing hard-coded.** Ports, paths, limits, lists, header names and words come from `agentcake/defaults.json`,
  `agentcake/data/` or the design tokens (`tools/check_hardcode.py`).
- **Small files, one job each.** A source file over 400 lines is split (`tools/check_size.py`, `tools/limits.json`),
  and each module has its test, `tests/test_<module>.py`.
- **The interface follows [`DESIGN.md`](DESIGN.md).** shadcn/ui components and the tokens of
  `web/src/styles/tokens.css` only; a new look is a new variant, added to DESIGN.md and to the component overview
  (`#/components`). An intended change to a page updates the visual baseline (`npm run visual:update`) in the same pull
  request.
- **No real personal data** in tests, fixtures, screenshots or examples: documentation address ranges only
  (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24), and no real e-mail addresses, names or replays.
- **Other people's code** names its source and licence in the file's header and gets a row in
  [`THIRD_PARTY.md`](THIRD_PARTY.md). Code whose licence is unclear isn't used.

## Pull requests

- **One change per pull request**, with a test that fails without it.
- **Commit messages in English**, saying what changed and why.
- **Name what it touches** in the description: the detection, the page script, the local pages, the server half or the
  documents.
