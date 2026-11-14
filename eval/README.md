# Evaluation

`agentcake eval` measures how Agent Cake judges sessions whose answers you know, and `agentcake eval --gate` compares
the measures with the thresholds in `thresholds.json`. Run it from a checkout of this repository
(`bin/agentcake eval`): an installed AgentCake does not carry this folder and says so. It only reads: it writes no
verdict and sends nothing.

    bin/agentcake eval [--gate] [--out DIR] [--sources FILE] [--cake-home DIR] [--truth-goal FILE] ...

`bin/agentcake eval --help` lists every option. With `--out`, the report is also written to `eval.md` and `eval.json`,
naming sessions by short hashes only.

## What this folder holds

| File | What it is |
|---|---|
| `thresholds.json` | The values `--gate` judges, one entry per measure (A1 to A9, N1 to N5), with the data sets each one reads |
| `named_user_agents.json` | Ten User-Agents of named AI products and the answer for each (measure A7) |
| `sources.example.json` | A template for `sources.json`: where this computer keeps your data |

A checkout also gives `agentcake eval` motion-attestation's 27 human captures (`tests/fixtures/motion_attestation`,
MIT): sessions that must never be called an agent.

## truth_goal.jsonl (your own labelled sessions)

Record sessions in an AgentCake whose answers you know (for example, visits you made yourself and visits an agent made
for you), list them in `truth_goal.jsonl` in this folder (or give `--truth-goal`), and point `--cake-home` at that
AgentCake's data folder (default: the current `CAKE_HOME`). One line per session, written after you checked it. The
session id never appears, only its short hash.

| Field | Meaning |
|---|---|
| `h` | `sha256("cake-goal|" + session id)[:12]` (cake.js's visit id in the CAKE_HOME's `sessions` table) |
| `case` | `T3`, `T5`, `T6`, `T8` or `T22`: an AI agent in a real browser, a hand-off between a human and an agent, an automated browser, a listed bot, a crawler script |
| `group` | what ran it, e.g. `claude-chrome`, `pw-humanlike-headed`, `googlebot-verified`, `googlebot-impersonated`, `uptimerobot`, `local-ai-tool`, `cloud-script` |
| `class` | the class it should get: `human`, `agent`, `mixed`, `bot` or `too_little_data` |
| `row`, `name`, `verification` | optional: `ai` or `automated`; the list id; `verified`, `self_reported` or `impersonation` |
| `crawler` | optional, `true`: the reasons must say "looks like a crawler" |
| `stretches` | optional, for a hand-off: `[[from_ms, to_ms, "agent" or "human"], ...]` in epoch ms, from the recorded times of the agent's last and the human's first action |
| `checked` | the day it was checked |

`sources.json` (copy `sources.example.json` into this folder, where git ignores it, or anywhere and give `--sources`)
names the same locations once instead of on every command: `cake_home`, `truth_goal`, `thresholds`,
`named_user_agents`.

## What the report says

One line per measure it could run, with its data set, the number of sessions, the result and, with `--gate`, the
threshold. A data set without a location is skipped and the report says what to give. With `--gate`, the exit code is 0
when every threshold this command measures passes, 1 when one fails or has no data (what did not run did not pass), and
2 for a usage error.

## README's figures

README's "What it can't tell yet" quotes three figures from one run of `agentcake eval` on the maintainers' data, with
AgentCake 0.4.0's code on 2026-11-13. That data is real people's sessions, so it is not in this repository and the run
can't be repeated from here; on your own labelled sessions (`truth_goal.jsonl`), the same measures describe your site.

- **17 of 23 Claude in Chrome replays judged agent.** Data: session replays that PostHog recorded on the maintainers'
  website, cut to the times a coding agent's log shows Claude in Chrome acting there: 30 replays, 23 of them with
  enough actions to judge. Counted: the behaviour model's verdict on those 23 (the report's scoreboard, row
  `posthog / claude-chrome`, "recall (evaluable)").
- **1 of 39 probably-human replays judged agent.** Data: the same website's replays outside those times, the site
  owner's own visits and other visitors': 95 replays, 39 of them with enough actions to judge. Counted: the same
  verdict on those 39 (row `all humans / rrweb`, "false positives (behaviour)"). Probably human, because an agent may
  have acted when no log shows it.
- **29.5% of hand-offs found within 3 seconds.** Data: 11 recordings a person made in a fresh browser profile on the
  maintainers' test pages, each spliced with each of 4 recordings of Claude in Chrome on their test page by the four
  patterns of `agentcake/data/splice.json` (such as 20 seconds of each, twice, with 1.5 seconds between stretches):
  176 sessions with 308 true hand-offs. Counted: a true hand-off is found when the session's timeline marks one
  within 3 seconds of it, as for 91 of the 308; the timeline marks none at all for 125 (the report's A5 line,
  `recording_splices`).

PostHog records no keys, no wheel and no `isTrusted`, so on its replays the behaviour model judges from less than
cake.js records; those replays are a reference, and `thresholds.json` gates none of them. The model fits no threshold
to any data (the report's "Thresholds set from data"), so its verdicts on these sets are held out. The percent a
session shows is calibrated on them and on the other sets with known answers, which changes no verdict.
