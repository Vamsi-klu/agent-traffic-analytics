# motion-attestation human captures

The 27 recorded human sessions of [motion-attestation](https://github.com/libcaptcha/motion-attestation) (MIT,
Copyright (c) 2026 libcaptcha; the licence text is `LICENSE.motion-attestation` in this folder), taken unchanged
from `test/fixtures/humans/` at commit `bea077b307e58d7a034a75fdaf84979f438cfdd7` (2026-09-10). Upstream describes
them as "27 recorded browser sessions across Chromium, LibreWolf, desktop and touch" and keeps them as real captures
only. They hold pointer positions, touch samples, key hold and gap times and scroll positions: no text, no key
identity, no address and no identifier of a person.

Used by `tests/test_motion_attestation.py` through `tests/motion_attestation.py` (job borrow-rules, plan decision
D33) as regression data: Agent Cake's behaviour layer must not call any of these people an agent.

| File | What it holds |
|---|---|
| `humans.json` | `source`: repository, commit, path and licence. `captures`: one entry per upstream file, in file-name order: `name` (the file name without `.json`), `browser` (`chromium` or `librewolf` where the file name says so, else null), `device` (`touch` when the capture has touch samples, else `desktop`), `upstream` (the file's content, values unchanged) and `raw` (the same capture converted to the records cake.js sends in its `r` stream, `docs/collect-format.md`). |
| `LICENSE.motion-attestation` | Upstream's MIT licence, which must travel with the copied data. |

The conversion only carries what upstream recorded; `tests/motion_attestation.py` explains each field. In short:
mouse samples become trusted `mousemove` records; touch samples become touch-pointer records (`pointerdown`,
`pointermove`, `pointerup`) plus `touchstart` and `touchend`, split into gestures on upstream's own 100 ms gap; keys
become `keydown` and `keyup` records with upstream's exact holds and gaps, as one typing stretch after the other
records (upstream does not record when typing happened); scroll samples become `scroll` records. Upstream's fixtures
hold no clicks, so there are none. Screen positions, movementX/Y, focus, visibility and key classes were never
recorded and are left out.

Rebuild (only if upstream's captures change) from a download of the repository at that commit:

```
python3 -I tests/motion_attestation.py <motion-attestation>/test/fixtures/humans
```
