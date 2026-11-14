"""Thresholds set from data, tested on data they were not set from (plan step S3.7, decision D36).

    build(sessions, settings, params=None) -> [{"rule", "feature", "operator", "shipped", "fitted", "by_site",
                                                "agents"}]
    fit(people, feature, operator, candidates, budget) -> the threshold, or None when no candidate keeps the budget

A rule whose threshold comes from data (settings "heldout.fitted") is fitted from people's segments alone, never from
an agent's: the candidate that makes the rule fire on the most segments while it fires on at most `budget` of the
measured segments (those where the feature has data) of every data set of people. So every agent product is held out
by construction: the agents table judges them with the threshold fitted on all the people. Held out by site: for
each site where people were recorded, the threshold is fitted again without that site's people, and the site's people
are judged with it; a threshold that only holds where it was fitted shows here as false positives. This is how Akamai
reports its research model (held out by customer) and why Charweb's grouped evaluation fell from 0.97 to 0.865
(research notes 19 and 21).

sessions: [{"source", "group", "product", "site", "truth", "events", "raw_input", "touch"}], one per session with
known answer (agentcake/evaluation/tables.py builds them). Each is measured once (features.session_features); a fold
only judges its own sessions again, with model.decide_segments() and the refitted threshold.
"""
import copy
import operator

from agentcake.detect import features, model

OPERATORS = {"<": operator.lt, ">": operator.gt}
FIRES_MORE_AS = {"<": max, ">": min}  # a larger threshold fires "<" on more segments, a smaller one ">"
HUMAN, AGENT = "human", "agent"
VALUE = 2  # protocol: a rule's condition is [feature, operator, value, value without data] (behavior_model.json)


def build(sessions, settings, params=None):
    params = params or model.load_params()
    measured = [_measure(s, params) for s in sessions]
    out = []
    for spec in settings["heldout"]["fitted"]:
        rule = next((r for r in params["rules"]["list"] if r["id"] == spec["rule"]), None)
        if rule is None:  # a model without this rule (an earlier version, judged for comparison) has nothing to fit
            continue
        feature, op, shipped = rule["all"][0][:VALUE + 1]  # the rule's first condition is the one set from data
        with_value = _Variants(params, spec["rule"])
        people = [m for m in measured if m["truth"] == HUMAN and not m.get("weak") and m["segments"] is not None]
        fitted = fit(people, feature, op, spec["candidates"], spec["budget"])
        by_site = []
        for site in sorted({m["site"] for m in people}):
            value = fit([m for m in people if m["site"] != site], feature, op, spec["candidates"], spec["budget"])
            here = [m for m in people if m["site"] == site]
            by_site.append({"site": site, "threshold": value, "people": len(here),
                            "false_positives": sum(_verdict(m, with_value(value)) == AGENT for m in here)})
        agents = {}
        for m in measured:
            if m["truth"] == AGENT and m["segments"] is not None:
                cell = agents.setdefault(f"{m['source']} / {m['product']}", {"sessions": 0, "agent": 0})
                cell["sessions"] += 1
                cell["agent"] += _verdict(m, with_value(fitted)) == AGENT
        out.append({"rule": spec["rule"], "feature": feature, "operator": op, "shipped": shipped, "fitted": fitted,
                    "budget": spec["budget"], "by_site": by_site, "agents": agents})
    return out


def fit(people, feature, op, candidates, budget):
    """The candidate that fires most while firing on at most `budget` of every data set's measured segments of
    people (any other session given is left out: an agent is never used)."""
    sets = {}
    for m in (m for m in people if m["truth"] == HUMAN and not m.get("weak")):
        values = [seg["features"][feature] for seg in m["segments"] if seg["features"][feature] is not None]
        sets.setdefault((m["source"], m["group"]), []).extend(values)
    within = [c for c in candidates
              if all(sum(OPERATORS[op](v, c) for v in values) <= budget * len(values) for values in sets.values())]
    return FIRES_MORE_AS[op](within) if within else None


def _measure(session, params):
    """The session with its measured segments, None when it is too little data (a phone, a tablet, few actions)."""
    events = sorted(session["events"], key=lambda e: e["t"])
    segments = None
    if not session["touch"]:
        segments = features.session_features(events, raw_input=session["raw_input"])
        if len(segments) < params["min_actions"]:
            segments = None
    return {**session, "events": events, "segments": segments}


def _verdict(measured, params):
    return model.decide_segments(measured["segments"], measured["events"], measured["raw_input"], params)["verdict"]


class _Variants:
    """The parameters with one rule's fitted threshold set to a value (the rule left out for None), made once each."""

    def __init__(self, params, rule_id):
        self.params, self.rule_id, self.made = params, rule_id, {}

    def __call__(self, value):
        if value not in self.made:
            changed = copy.deepcopy(self.params)
            rules = changed["rules"]["list"]
            if value is None:
                changed["rules"]["list"] = [r for r in rules if r["id"] != self.rule_id]
            else:
                next(r for r in rules if r["id"] == self.rule_id)["all"][0][VALUE] = value
            self.made[value] = changed
        return self.made[value]
