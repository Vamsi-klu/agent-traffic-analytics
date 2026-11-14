"""Named programs and bots: GOAL A7 (10 named User-Agents) and T22 / A9 (listed bots vs automated browsers).

    named_table(rows) -> {"n", "right", "rows": [{"name", "class", "kind", "verification", "right"}]}
    t22_table(rows, settings) -> {"groups": {group: {"n", "right", "classes", "crawler_reason"}}, "n", "right"}

A7 rows come from sessions.named(): each User-Agent judged as a local session with nothing else known, so a Bot is
"self-reported only" (D17: on this computer nothing can be verified). T22 rows are CAKE_HOME sessions whose truth
line has case T22 and a group (googlebot-verified, googlebot-impersonated, uptimerobot, local-ai-tool, cloud-script,
...): right means the class, row and verification the line gives; crawler_reason counts the sessions whose reasons
hold the crawler-like weak signal (data/eval.json "reasons.crawler"), which never changes the class (D17).
"""
from agentcake.evaluation import sessions

T22 = "T22"


def named_table(rows):
    out = [{"name": r["truth"]["name"], "class": r["class"], "said_name": r["name"], "kind": r["kind"],
            "verification": r["verification"], "right": sessions.right(r)} for r in rows]
    return {"n": len(out), "right": sum(r["right"] for r in out), "rows": out}


def t22_table(rows, settings):
    crawler = settings["reasons"]["crawler"]
    groups = {}
    for r in rows:
        if r["truth"].get("case") != T22:
            continue
        cell = groups.setdefault(r["group"], {"n": 0, "right": 0, "classes": {}, "crawler_reason": 0,
                                              "crawler_expected": 0})
        cell["n"] += 1
        ok = sessions.right(r)
        if r["truth"].get("crawler"):
            cell["crawler_expected"] += 1
            ok = ok and crawler in r["reasons"]
        cell["right"] += ok
        cell["crawler_reason"] += crawler in r["reasons"]
        label = r["class"] + (f" · {r['row']}" if r["row"] else "") + \
            (f" ({r['verification']})" if r["verification"] else "")
        cell["classes"][label] = cell["classes"].get(label, 0) + 1
    return {"groups": groups, "n": sum(g["n"] for g in groups.values()),
            "right": sum(g["right"] for g in groups.values())}
