"""What each part of Agent Cake finds alone and together (each layer alone against all of them).

    by_half(rows, settings) -> [{"keep", "groups": {group: {"n", "right"}}, "n", "right"}]
    by_layer(rows, settings) -> the same for the judging layers

by_half judges each session again with only some halves of its evidence (data/eval.json "layers.configurations":
the page script alone, the collect endpoint alone, the server half alone, page + collector, all three); by_layer
with only some judging layers (behaviour alone, environment alone, name + verification, all four). Right means the
class, and the row when the answer has one (sessions.right). Only rows whose evidence has more than behaviour take
part (a PostHog replay has no halves to take away). Nothing is stored: each configuration is one verdict.decide().
"""
from agentcake.detect import verdict
from agentcake.evaluation import evidence as evidence_builder, sessions


def by_half(rows, settings):
    return _table(rows, settings["layers"]["configurations"], "halves")


def by_layer(rows, settings):
    return _table(rows, settings["layers"]["judging_layers"], "layers")


def _table(rows, configurations, kind):
    rows = [r for r in rows if r["evidence"].get("env") is not None]
    out = []
    for keep in configurations:
        groups = {}
        for r in rows:
            kept = evidence_builder.keep(r["evidence"], **{kind: keep})
            result = verdict.decide(kept)
            ok = sessions.right(dict(r, **{"class": result["class"], "row": result["row"], "name": result["name"],
                                           "kind": result["kind"], "verification": result["verification"]}))
            cell = groups.setdefault(f"{r['source']} / {r['group']}", {"n": 0, "right": 0, "classes": {}})
            cell["n"] += 1
            cell["right"] += ok
            label = result["class"] + (f" · {result['row']}" if result["row"] else "")
            cell["classes"][label] = cell["classes"].get(label, 0) + 1
        out.append({"keep": list(keep), "groups": groups, "n": sum(g["n"] for g in groups.values()),
                    "right": sum(g["right"] for g in groups.values())})
    return out
