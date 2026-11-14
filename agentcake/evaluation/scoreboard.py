"""The behaviour layer's scoreboard, reported the way the industry reports (plan step S3.7, decision D36).

    build(rows, takeover_rows, settings, limit_s) -> {"agents", "humans", "pooled_humans", "precision", "sites",
                                                      "mixed"}

What it reports, after Akamai's research prototype and AgentShield (research note 21, sections 4 and 5):
- agents: per data set and agent product, how many sessions there were, how many had enough actions to judge
  (the evaluable share; the rest is "too little data"), and how many of those the behaviour model called an agent
  (recall on the evaluable ones, and on all of them, which is what a site sees), beside what the four layers called
  them (agent or mixed).
- humans: per data set and group, the sessions the behaviour model called an agent (false positives), and what the
  four layers called agent or mixed; every rate with its exact 95% interval (stats.clopper_pearson).
- pooled_humans: the human data sets added up, one pool per recording kind (raw cake.js events, or rrweb only),
  without weak answers (the site owner's presumed humans in S9.2's PostHog set, listed in humans on their own).
- precision: for each agent product, the share of sessions called agent that would be agents if agents were 1% or
  5% of all sessions, with the human false positive rate of the same recording kind, as measured and at its upper
  bound.
- sites: the same counts per site, so that a rule that only holds on one site shows.
- mixed: per data set of mixed sessions, the per-action accuracy, the agent-share error and the hand-offs (A3-A5, as
  takeovers.summary() measures them).

Rows are sessions.row()'s; a row may carry "site" (where it was recorded) and its group names the agent product
through settings "scoreboard.products". Nothing is judged here: every verdict is already on the rows.
"""
from agentcake.evaluation import stats, takeovers

AGENT, HUMAN = "agent", "human"
AGENTLIKE = ("agent", "mixed")
TOO_LITTLE = "too_little_data"


def build(rows, takeover_rows, settings, limit_s):
    board = settings["scoreboard"]
    agents = _members(rows, board["agent_sources"], AGENT, board)
    humans = _members(rows, board["human_sources"], HUMAN, board)
    confidence = board["confidence"]
    agent_cells = [_agent_cell(key, members, confidence) for key, members in _grouped(agents, ("source", "product"))]
    human_cells = [_human_cell(key, members, confidence) for key, members in _grouped(humans, ("source", "group"))]
    pools = {kind: _human_cell({"recording": kind}, [m for m in humans if m["recording"] == kind and not m["weak"]],
                               confidence)
             for kind in sorted({m["recording"] for m in humans})}  # weak answers (see tables.posthog_truth) apart
    return {"agents": agent_cells, "humans": human_cells, "pooled_humans": pools,
            "precision": [_precision(cell, pools, board) for cell in agent_cells],
            "sites": _sites(agents, [m for m in humans if not m["weak"]], confidence),
            "mixed": {source: takeovers.summary(items, "verdict", limit_s)
                      for source, items in takeover_rows.items() if items}}


def _members(rows, sources, truth_class, board):
    """The rows of these sources whose answer is truth_class, each reduced to what the scoreboard counts."""
    out = []
    for source in sources:
        for r in rows.get(source, []):
            if r["truth"].get("class") != truth_class:
                continue
            out.append({"source": source, "group": r["group"], "weak": bool(r["truth"].get("weak")),
                        "product": board["products"].get(r["group"], r["group"]),
                        "site": r.get("site") or board["sites"].get(source, source),
                        "recording": board["recording"].get(source, source),
                        "evaluable": r["behaviour"] not in (None, TOO_LITTLE),
                        "behaviour_agent": r["behaviour"] == AGENT,
                        "four_layer_agent": r["class"] in AGENTLIKE})
    return out


def _grouped(members, keys):
    groups = {}
    for m in members:
        groups.setdefault(tuple(m[k] for k in keys), []).append(m)
    return [(dict(zip(keys, key), recording=items[0]["recording"]), items) for key, items in groups.items()]


def _rate(k, n, confidence):
    low, high = stats.clopper_pearson(k, n, confidence)
    return {"k": k, "n": n, "value": k / n if n else None, "low": low, "high": high}


def _agent_cell(key, members, confidence):
    evaluable = [m for m in members if m["evaluable"]]
    caught = sum(m["behaviour_agent"] for m in evaluable)
    return {**key, "sessions": len(members),
            "evaluable": _rate(len(evaluable), len(members), confidence),
            "recall": _rate(caught, len(evaluable), confidence),
            "recall_all": _rate(caught, len(members), confidence),
            "four_layers": _rate(sum(m["four_layer_agent"] for m in members), len(members), confidence)}


def _human_cell(key, members, confidence):
    evaluable = [m for m in members if m["evaluable"]]
    return {**key, "sessions": len(members),
            "evaluable": _rate(len(evaluable), len(members), confidence),
            "false_positives": _rate(sum(m["behaviour_agent"] for m in evaluable), len(evaluable), confidence),
            "four_layers": _rate(sum(m["four_layer_agent"] for m in members), len(members), confidence)}


def _precision(cell, pools, board):
    """Precision at each prevalence of the board, from the cell's recall (evaluable sessions) and the false positive
    rate of the humans recorded the same way: as measured, and at its upper bound."""
    pool = pools.get(cell["recording"])
    fp = pool["false_positives"] if pool else {"value": None, "high": None, "n": 0}
    recall = cell["recall"]["value"]
    return {"source": cell["source"], "product": cell["product"], "recall": recall, "humans": fp["n"],
            "false_positive_rate": fp["value"], "false_positive_high": fp["high"],
            "at": {str(prevalence): {"measured": stats.precision_at(recall, fp["value"], prevalence),
                                     "bound": stats.precision_at(recall, fp["high"], prevalence)}
                   for prevalence in board["prevalences"]}}


def _sites(agents, humans, confidence):
    out = {}
    for site in sorted({m["site"] for m in agents + humans}):
        site_agents = [m for m in agents if m["site"] == site]
        site_humans = [m for m in humans if m["site"] == site]
        out[site] = {"agents": _agent_cell({}, site_agents, confidence) if site_agents else None,
                     "humans": _human_cell({}, site_humans, confidence) if site_humans else None}
    return out
