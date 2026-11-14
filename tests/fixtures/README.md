# Test fixtures

Data the tests read: made-up data, and third-party data whose licence lets it be passed on.

| Folder or file | What it is |
|---|---|
| `env_rules/cases.json` | Hand-written hit and miss cases of every environment rule, on an ordinary Chrome with made-up values |
| `judge_0_3_4/model.json` | cake 0.3.4's hand-set model parameters, the reference `agentcake/detect/timeline.py` is checked against |
| `motion_attestation/` | motion-attestation's 27 human captures (MIT, with their licence), regression data for the behaviour layer |

`tests/synthetic_sessions.py` writes made-up visits by rule for the tests that need a session with enough actions,
`tests/vectors/` holds the middleware's made-up test vectors, and `web/src/data/fixtures/` the local pages' samples.

Agent Cake's own recordings (the behaviour lab's sessions, real cake.js uploads of the demo shop) and the tests on
them stay with the maintainers and are not published; the model's parameters that come from them are
(`agentcake/data/`).
