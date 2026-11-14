"""Sessions where a human and an agent took turns: who did each action, the shares and the hand-offs (GOAL A3-A5).

    session_row(evidence, truth_at, true_handoffs, limit_s) -> row      one mixed session, both views
    splice_rows(agents, humans, raw_input, limit_s) -> rows             every agent with every human by every pattern
    summary(rows, view, limit_s) -> {"sessions", "accuracy", "share_error", "handoff", ...}

Two views of the same session. model: the behaviour model's timeline, who did each action (S3.7's numbers). verdict:
what Agent Cake shows, the four-layer class deciding it (verdict._segments): an Agent's or a Human's decided actions
are all that actor's, a Mixed session keeps each action's own who, and only a Mixed session has hand-offs. The gate
judges the verdict view; the model view is printed beside it.

Accuracy counts the decided actions (A3); the share error is in percentage points by action (A4); a hand-off error is
the distance from a true hand-off to the nearest predicted one, None when there is none (A5). Truth comes from a
splice's stretches, a T5 session's recorded hand-off, or a mixed replay's agent units.
"""
import statistics

from agentcake.detect import verdict
from agentcake.evaluation import evidence as evidence_builder, scoring, splice

VIEWS = ("model", "verdict")
WHOLE_CLASSES = ("agent", "human")
UNSURE = "unsure"


def session_row(evidence, truth_at, true_handoffs, limit_s):
    """One mixed session: its class and, per view, the action scores and hand-off errors (see the module docstring)."""
    result = verdict.decide(evidence)
    behaviour = evidence.get("behavior") or {}
    line = behaviour.get("timeline")
    row = {"class": result["class"], "row": result["row"], "behaviour": behaviour.get("verdict"),
           "true_handoffs": len(true_handoffs)}
    if not line:
        for view in VIEWS:
            row[view] = None
        return row
    actions = [(a, truth_at(a["t"])) for a in line["actions"]]
    kept = [(a, who) for a, who in actions if who is not None]  # actions in the gaps of a splice have no answer
    predicted = {"model": [h["t"] for h in line["handoffs"]], "verdict": [h["t"] for h in result["handoffs"]]}
    for view in VIEWS:
        said = [a["who"] if view == "model" else verdict_who(a["who"], result["class"]) for a, _ in kept]
        errors, extra = scoring.handoff_errors(predicted[view], true_handoffs)
        row[view] = {**scoring.action_scores(said, [who for _, who in kept]), "handoff_errors_s": errors,
                     "handoffs_extra": extra, "handoffs_found_within": scoring.share_within(errors, limit_s)}
    return row


def verdict_who(model_who, cls):
    """An action's who as the verdict shows it: the whole class for Agent and Human, the model's own otherwise."""
    return cls if (cls in WHOLE_CLASSES and model_who != UNSURE) else model_who


def splice_rows(agents, humans, raw_input, limit_s, params=None):
    """agents, humans: [(name, events)]; each agent with each human by each pattern of data/splice.json."""
    params = params or splice.load_params()
    rows = []
    for agent_name, agent_events in agents:
        for human_name, human_events in humans:
            for pattern_name, pattern in params["patterns"].items():
                spliced = splice.build(agent_events, human_events, pattern, params)
                if spliced is None:
                    continue
                truth = spliced["truth"]
                built = evidence_builder.behaviour_only(spliced["events"], raw_input)
                rows.append({"agent": agent_name, "human": human_name, "pattern": pattern_name,
                             **session_row(built, lambda t, truth=truth: splice.who_at(truth, t),
                                           [t for t, _, _ in splice.boundaries(truth)], limit_s)})
    return rows


def summary(rows, view, limit_s):
    """The A3, A4 and A5 numbers of one view over the rows that could be scored."""
    scored = [r[view] for r in rows if r.get(view) and r[view]["n"]]
    errors = [e for s in scored for e in s["handoff_errors_s"]]
    found = [e for e in errors if e is not None]
    missed = sum(1 for e in errors if e is None)
    return {"sessions": len(rows), "scored": len(scored), "actions": sum(s["n"] for s in scored),
            "classes": _count(r["class"] for r in rows),
            "accuracy_decided": scoring.summary([s["accuracy_decided"] for s in scored]),
            "share_error_pp": scoring.summary([s["share_error_pp"] for s in scored]),
            "handoffs_true": len(errors), "handoffs_missed": missed,
            "handoff_error_s": scoring.summary(found),
            "handoffs_within_limit": scoring.share_within(errors, limit_s),
            "largest_handoff_error_s": (max(found) if found else None) if not missed else None,
            "handoffs_extra": sum(s["handoffs_extra"] for s in scored)}


def by_pattern(rows, view):
    """Per splice pattern: how many splices, and their median share error and hand-off error (the lab's table)."""
    out = {}
    for name in sorted({r["pattern"] for r in rows if "pattern" in r}):
        members = [r[view] for r in rows if r.get("pattern") == name and r.get(view)]
        errors = [e for m in members for e in m["handoff_errors_s"] if e is not None]
        out[name] = {"splices": len(members),
                     "share_error_pp_median": _median([m["share_error_pp"] for m in members]),
                     "handoff_error_s_median": _median(errors)}
    return out


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _count(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out
