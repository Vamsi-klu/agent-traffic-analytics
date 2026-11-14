"""Write agentcake/data/reasons_past.json: every wording a reason had before verdicts kept their facts.

    python3 -I -B tools/reasons_past.py [--until <commit>] [--check]      (from the repository root; default: HEAD)

Until verdicts kept each reason's facts, a session kept only the finished sentence. agentcake/detect/reasons_past.py
reads such a sentence back into facts by matching it against every wording that could have made it, so that it can be
worded anew (the words are display). This collects those wordings from every commit up to --until that changed
the files they come from: reasons.json (the reasons and the phrases a fact names: halves, methods, behavior_basis,
crawler_signals, durations), agent_markers.json (each mark's text and the spans) and webbotauth.json (each result's
reason). Newest first, each wording once. A commit that already has FACTS_COMMIT (verdicts keep facts from there
on) is skipped: what its build judged needs no reading back. A branch made before it and merged later (a build that
judged sessions with its own wordings) is collected, so run this again after such a merge; --check says whether the
file is still complete (tests/test_verdict_text.py runs it when git history is there).
"""
import argparse
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "agentcake", "data", "reasons_past.json")
FILES = {"reasons": "agentcake/data/reasons.json", "markers": "agentcake/data/agent_markers.json",
         "webbotauth": "agentcake/data/webbotauth.json"}
PHRASES = ("halves", "methods", "behavior_basis", "crawler_signals", "durations")
FACTS_COMMIT = "30ee5f1"  # the first commit whose verdicts keep each reason's facts
COMMENT = ("Every wording a reason had before verdicts kept their facts (tools/reasons_past.py collects them from the "
           f"commits without {FACTS_COMMIT}; newest first). agentcake/detect/reasons_past.py matches a kept sentence "
           "against these to read its facts back, so that it is worded anew. Not interface text: never shown.")


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def _versions(path, until):
    """The file as each commit up to `until` that changed it left it, newest first."""
    for commit in _git("log", "--format=%H", until, "--", path).split():
        if _has_facts(commit):
            continue
        try:
            yield json.loads(_git("show", f"{commit}:{path}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue


def _has_facts(commit):
    return subprocess.run(["git", "merge-base", "--is-ancestor", FACTS_COMMIT, commit], cwd=ROOT,
                          capture_output=True).returncode == 0


def _add(table, key, text):
    if isinstance(text, str) and text not in table.setdefault(key, []):
        table[key].append(text)


def collect(until):
    out = {"reasons": {}, **{name: {} for name in PHRASES}, "markers": {}, "spans": {}, "webbotauth": {}}
    for data in _versions(FILES["reasons"], until):
        for reason_id, entry in data.get("reasons", {}).items():
            _add(out["reasons"], reason_id, entry.get("text"))
        for name in PHRASES:
            for key, text in data.get(name, {}).items():
                _add(out[name], key, text)
    for data in _versions(FILES["markers"], until):
        for mark_id, meta in data.get("markers", {}).items():
            _add(out["markers"], mark_id, meta.get("text"))
        for key, text in data.get("spans", {}).items():
            _add(out["spans"], key, text)
    for data in _versions(FILES["webbotauth"], until):
        for code, text in data.get("reasons", {}).items():
            if not code.startswith("$"):
                _add(out["webbotauth"], code, text)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--until", default="HEAD")
    parser.add_argument("--check", action="store_true", help="say whether the file is complete; change nothing")
    args = parser.parse_args()
    data = {"$comment": COMMENT, **collect(args.until)}
    if args.check:
        with open(OUT, encoding="utf-8") as handle:
            kept = json.load(handle)
        missing = {table: sorted(key for key, texts in values.items()
                                 if not set(texts) <= set(kept.get(table, {}).get(key, ())))
                   for table, values in data.items() if isinstance(values, dict)}
        missing = {table: keys for table, keys in missing.items() if keys}
        print(f"{os.path.relpath(OUT, ROOT)}: " + (f"missing wordings of {missing}; run tools/reasons_past.py" if missing
                                                    else "every wording from before facts were kept is there"))
        return 1 if missing else 0
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print(f"{os.path.relpath(OUT, ROOT)}: {sum(len(v) for v in data['reasons'].values())} reason wordings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
