"""The four layers on sessions known to be human: everything that could call a human an agent (GOAL A1, plan S3.9).

    table(rows) -> {"sessions": [per session], "rules": {rule id: {...}}, "summary": counts}

A1 counts only the class. This table shows how close each layer came, one session per row: every environment rule
that held (hard, soft or weak, S3.3) and how many distinct soft or hard rules held together (S3.4 counts a soft hit
when another rule that is not weak holds too); the longest run of actions the behaviour timeline gave an agent,
against verdict.json "mixed" (a run that long, with a long human run, makes a session Mixed); and the crawler check's
patterns (a datacenter address, page loads or visits at fixed intervals, many pages in a row; two of them write
"looks like a crawler", S3.4); S3.8's weak-signal reasons (rhythm, window jumps, ...), which never change a class.
Per rule: in how many sessions it held, and in how many it could not be checked because the session did not record
its inputs.
"""
from agentcake.detect import crawler, env_rules, verdict
from agentcake.units import MS_PER_S

WEAK = "weak"
WEAK_PREFIX = "weak."  # the ids of S3.8's weak-signal reasons (agentcake/data/reasons.json)


def table(rows):
    settings = verdict.load_settings()
    long_run = settings["mixed"]
    out, rules = [], {}
    for r in rows:
        evidence = r["evidence"]
        env = evidence.get("env")
        hits = list(env.hits) if env else []
        strong = sorted({h.rule for h in hits if h.strength != WEAK})
        agent_runs = [run for run in ((evidence.get("behavior") or {}).get("timeline") or {}).get("runs") or []
                      if run["who"] == "agent"]
        longest = max(agent_runs, key=lambda run: (run["n"], run["end"] - run["start"]), default=None)
        found = crawler.patterns([page.get("t") for page in evidence.get("pages") or []], evidence.get("network"),
                                 evidence.get("visits") or ())
        out.append({"id": r["id"], "class": r["class"], "behaviour": r["behaviour"], "n_actions": r["n_actions"],
                    "env_hits": {h.rule: h.strength for h in hits}, "strong_rules": strong,
                    "soft_would_count": len(strong) > 1,
                    "longest_agent_run": {"n": longest["n"], "span_s": (longest["end"] - longest["start"]) / MS_PER_S,
                                          "long": longest["n"] >= long_run["min_actions"] and
                                          (longest["end"] - longest["start"]) / MS_PER_S >= long_run["min_span_s"]}
                    if longest else None,
                    "weak_reasons": [reason for reason in r["reasons"] if reason.startswith(WEAK_PREFIX)],
                    "crawler": {name: found[name] for name in crawler.PATTERNS},
                    "looks_like_crawler": crawler.looks_like_crawler(found)})
        for hit in hits:
            rules.setdefault(hit.rule, {"strength": hit.strength, "half": hit.half, "held": 0, "unknown": 0})
            rules[hit.rule]["held"] += 1
        for rule_id in env.unknown if env else ():
            rule = env_rules.load_rules().rule(rule_id)
            rules.setdefault(rule_id, {"strength": rule.strength, "half": rule.half, "held": 0, "unknown": 0})
            rules[rule_id]["unknown"] += 1
    return {"sessions": out, "rules": rules, "summary": _summary(out, rules)}


def _summary(sessions, rules):
    table_rules = env_rules.load_rules().rules
    return {"sessions": len(sessions), "classes": _count(s["class"] for s in sessions),
            "rules_in_table": len(table_rules), "rules_on": sum(1 for rule in table_rules if rule.enabled),
            "rules_held": {strength: sorted(rule for rule, cell in rules.items()
                                            if cell["held"] and cell["strength"] == strength)
                           for strength in ("hard", "soft", WEAK)},
            "sessions_with_a_strong_hit": sum(1 for s in sessions if s["strong_rules"]),
            "sessions_where_soft_hits_would_count": sum(1 for s in sessions if s["soft_would_count"]),
            "sessions_with_a_long_agent_run": sum(1 for s in sessions if (s["longest_agent_run"] or {}).get("long")),
            "sessions_looking_like_a_crawler": sum(1 for s in sessions if s["looks_like_crawler"]),
            "weak_reasons": _count(reason for s in sessions for reason in s["weak_reasons"])}


def _count(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out
