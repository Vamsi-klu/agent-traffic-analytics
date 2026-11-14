"""The matching half of the content-blocker check: runs only inside the throwaway venv that check.py makes, where the
pinned `adblock` package (Brave's adblock-rust; tools/blockers/blockers.json "matcher") is installed. Never imported by
AgentCake or by check.py.

    <venv>/bin/python -I match.py <job.json> <answer.json>

job.json: {"lists": [{"blocker", "name", "path", "hosts", "standard_first_party"}], "requests": [{"url", "type",
"page", "first_party"}]}. For each request and each blocker, the answer says whether all of the blocker's lists
together block it (an exception in one list cancels a block in another, as in the blocker), with which rule, and which
of its lists hold a matching rule. Brave is answered twice: in its default Standard mode a first-party request is
checked only against the lists without first-party protections; in Aggressive mode against all of them.
"""
import json
import sys

import adblock


def engine(lists):
    rules = adblock.FilterSet(debug=True)
    for item in lists:
        with open(item["path"], encoding="utf-8", errors="replace") as f:
            rules.add_filter_list(f.read(), format="hosts" if item["hosts"] else "standard")
    return adblock.Engine(filter_set=rules, optimize=False)


def verdict(found):
    return {"blocked": bool(found.matched and not found.exception), "rule": found.filter, "exception": found.exception}


def main(job_path, answer_path):
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    blockers = sorted({item["blocker"] for item in job["lists"]})
    whole = {b: engine([i for i in job["lists"] if i["blocker"] == b]) for b in blockers}
    standard_first_party = engine([i for i in job["lists"] if i["blocker"] == "Brave" and i["standard_first_party"]])
    single = [(item, engine([item])) for item in job["lists"]]
    answers = []
    for req in job["requests"]:
        def check(eng):
            return eng.check_network_urls(req["url"], req["page"], req["type"])
        row = {}
        for b in blockers:
            hits = [{"list": item["name"], "rule": found.filter, "exception": found.exception}
                    for item, eng in single if item["blocker"] == b
                    for found in [check(eng)] if found.matched or found.exception]
            if b == "Brave":
                std = standard_first_party if req["first_party"] else whole[b]
                row["Brave (Standard)"] = dict(verdict(check(std)), lists=hits)
                row["Brave (Aggressive)"] = dict(verdict(check(whole[b])), lists=hits)
            else:
                row[b] = dict(verdict(check(whole[b])), lists=hits)
        answers.append(row)
    with open(answer_path, "w", encoding="utf-8") as f:
        json.dump(answers, f)


if __name__ == "__main__":
    main(*sys.argv[1:3])
