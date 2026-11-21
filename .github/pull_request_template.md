## What and why

<!-- One change per pull request. Link the issue it fixes, and say what it touches: the detection, the page script,
the local pages, the server middleware or the documents. -->

## Checklist

- [ ] A test that fails without this change
- [ ] For rule or model changes, include `agentcake eval` results from before and after the change. Your change must
      not misclassify more humans as agents.
- [ ] `python3 -I -m unittest discover -s tests -v` passes
- [ ] `python3 tools/check_hardcode.py`, `python3 tools/check_imports.py` and `python3 tools/check_size.py` report 0
- [ ] A change to the local pages follows `DESIGN.md` and passes `npm run check:ui`, `npm run build`
      and `npm run visual` (with the new baseline when the change is intended)
- [ ] No real personal data in tests, fixtures, screenshots or examples
- [ ] Other people's code names its source and licence, with a row in `THIRD_PARTY.md`
