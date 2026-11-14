"""Scores of the behaviour model against known answers: the arithmetic behind thresholds A1–A5.

- action_scores(labels, truth): one session's actions (or action segments), the model's who against the true who:
  accuracy over the decided ones (A3; unsure ones left out, as our study of PostHog replays counted) and over all of them (the lab's),
  the agent share and its error in percentage points (A4), the unsure share.
- handoff_errors(predicted, true): for each true hand-off, the distance in seconds to the nearest predicted one in
  the same direction, human to agent or agent to human (None when the model predicted none that way, a missed
  hand-off: one found only the other way round found nothing), and how many predicted ones were extra (A5).
- summary(values): count, median, p90 and max, the way the lab summarised its splices.

Ported from our own code: the behaviour lab's analyze.py (acc, shares_of) and
splice.py (switch_errors; 2026-11-11), cake-ph-eval/mixed_eval.py (2026-11-12). Moved from the research tools,
unchanged, so that `agentcake eval` and the research tools share it.
"""
import statistics

from agentcake.units import MS_PER_S, PERCENT

P90 = 0.9  # protocol: the lab's 90th percentile, sorted(values)[int(0.9 * (n - 1))]


def action_scores(labels, truth):
    """labels: "agent" / "human" / "unsure" per action; truth: "agent" / "human" per action, same order."""
    n = len(labels)
    decided = [(said, true) for said, true in zip(labels, truth) if said != "unsure"]
    correct = sum(1 for said, true in decided if said == true)
    agent_share = labels.count("agent") / n if n else None
    truth_share = truth.count("agent") / n if n else None
    return {"n": n, "decided": len(decided), "correct": correct,
            "accuracy_decided": correct / len(decided) if decided else None,
            "accuracy_all": correct / n if n else None,
            "agent_share": agent_share, "truth_agent_share": truth_share,
            "share_error_pp": abs(agent_share - truth_share) * PERCENT if n else None,
            "unsure_share": (n - len(decided)) / n if n else None}


def handoff_errors(predicted, true):
    """predicted, true: hand-offs as (t in ms, from, to). Returns (errors in s per true hand-off, extra predicted
    ones): each true hand-off's distance to the nearest predicted one of the same direction, None when there is none."""
    errors = []
    for t, before, after in true:
        same_way = [p for p, p_before, p_after in predicted if (p_before, p_after) == (before, after)]
        errors.append(min(abs(t - p) for p in same_way) / MS_PER_S if same_way else None)
    return errors, max(0, len(predicted) - len(true))


def summary(values):
    """{"n", "median", "p90", "max"} of the values that are not None (None when there is none)."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None}
    return {"n": len(values), "median": statistics.median(values), "p90": values[int(P90 * (len(values) - 1))],
            "max": values[-1]}


def share_within(values, limit):
    """Share of the values at or under the limit; None values (misses) count as over it."""
    return sum(1 for v in values if v is not None and v <= limit) / len(values) if values else None
