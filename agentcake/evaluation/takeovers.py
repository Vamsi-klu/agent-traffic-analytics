"""Sessions where a human and an agent took turns: who did each action, the shares and the hand-offs (thresholds A3-A5).

    session_row(evidence, truth_at, true_handoffs, limit_s) -> row      one mixed session, both views; true_handoffs:
                                                                        [(t, from, to)] (splice.boundaries)
    splice_rows(agents, humans, raw_input, limit_s) -> rows             every agent with every human by every pattern
    summary(rows, view, limit_s) -> {"sessions", "accuracy", "share_error", "handoff", ..., "mixed_found", "in_mixed"}

Two views of the same session. model: the behaviour model's timeline, who did each action (the model's own numbers). verdict:
what AgentCake shows, the four-layer class deciding it (verdict._segments): an Agent's or a Human's decided actions
are all that actor's, a Mixed session keeps each action's own who, and only a Mixed session has hand-offs. The gate
judges the verdict view; the model view is printed beside it.

Accuracy counts the decided actions (A3); the share error is in percentage points by action (A4); a hand-off error is
the distance from a true hand-off to the nearest predicted one in the same direction, None when there is none
(A5: a hand-off found the other way round, an agent's where a human took over, is not found). Truth comes from a
splice's stretches, a T5 session's recorded hand-off, or a mixed replay's agent units.
"""
import math
import statistics

from agentcake.detect import verdict
from agentcake.evaluation import evidence as evidence_builder, scoring, splice
from agentcake.evaluation.stats import median, tally

VIEWS = ("model", "verdict")
WHOLE_CLASSES = ("agent", "human")
UNSURE = "unsure"
MIXED = "mixed"  # Human + agent: the only class with hand-offs (verdict.py)


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
    predicted = {"model": [(h["t"], h["from"], h["to"]) for h in line["handoffs"]],
                 "verdict": [(h["t"], h["from"], h["to"]) for h in result["handoffs"]]}
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
    rows = []
    for agent, human, pattern, spliced in splice.each(agents, humans, params or splice.load_params()):
        truth = spliced["truth"]
        built = evidence_builder.behaviour_only(spliced["events"], raw_input)
        rows.append({"agent": agent, "human": human, "pattern": pattern,
                     **session_row(built, lambda t, truth=truth: splice.who_at(truth, t), splice.boundaries(truth),
                                   limit_s)})
    return rows


def summary(rows, view, limit_s):
    """The A3, A4 and A5 numbers of one view over the rows that could be scored: the action scores, the numbers of
    every true hand-off, how many of the mixed sessions were judged Human + agent (mixed_found, {"count", "n"}) and
    the hand-off numbers of those sessions alone (in_mixed), whose median error A5 judges. Only a session judged
    Human + agent shows hand-offs: one with too few agent actions to tell is judged Human, and missing an agent that
    way is the safe side of calling a human one, so A5 measures the hand-offs where the product shows them."""
    scored = [r[view] for r in rows if r.get(view) and r[view]["n"]]
    in_mixed = [r[view] for r in rows if r["class"] == MIXED and r.get(view) and r[view]["n"]]
    return {"sessions": len(rows), "scored": len(scored), "actions": sum(s["n"] for s in scored),
            "classes": tally(r["class"] for r in rows),
            "accuracy_decided": scoring.summary([s["accuracy_decided"] for s in scored]),
            "share_error_pp": scoring.summary([s["share_error_pp"] for s in scored]),
            **_handoffs(scored, limit_s),
            "mixed_found": {"count": sum(1 for r in rows if r["class"] == MIXED), "n": len(rows)},
            "in_mixed": _handoffs(in_mixed, limit_s)}


def _handoffs(scored, limit_s):
    """The hand-off numbers of scored session views: true ones, missed, errors of the found ones, share within the
    limit, the median and the largest of every error (unknown when it is a miss: a miss is over any limit), extra
    predicted ones."""
    errors = [e for s in scored for e in s["handoff_errors_s"]]
    found = [e for e in errors if e is not None]
    missed = sum(1 for e in errors if e is None)
    return {"handoffs_true": len(errors), "handoffs_missed": missed,
            "handoff_error_s": scoring.summary(found),
            "handoff_error_median_s": _median_counting_misses(errors),
            "handoffs_within_limit": scoring.share_within(errors, limit_s),
            "largest_handoff_error_s": (max(found) if found else None) if not missed else None,
            "handoffs_extra": sum(s["handoffs_extra"] for s in scored)}


def _median_counting_misses(errors):
    """The median of hand-off errors in which a miss (None) is larger than any error, rather than left out: None when
    the median is a miss, so over any limit, or when there is no error at all."""
    if not errors:
        return None
    middle = statistics.median([math.inf if e is None else e for e in errors])
    return None if math.isinf(middle) else middle


def by_pattern(rows, view):
    """Per splice pattern: how many splices, and their median share error and hand-off error (the lab's table)."""
    out = {}
    for name in sorted({r["pattern"] for r in rows if "pattern" in r}):
        members = [r[view] for r in rows if r.get("pattern") == name and r.get(view)]
        errors = [e for m in members for e in m["handoff_errors_s"] if e is not None]
        out[name] = {"splices": len(members),
                     "share_error_pp_median": median([m["share_error_pp"] for m in members]),
                     "handoff_error_s_median": median(errors)}
    return out
