"""Calibration of the percents a verdict shows (plan step S3.7, decision D36): fitting the behaviour map, and checking
every percent against sessions with known answers.

    fit(points, prior_count) -> blocks [[upper score, chance of an agent]], non-decreasing (the map confidence.py reads)
    check(pairs, bins) -> {"bins": [...], "brier", "brier_natural", "sessions"}: reliability of chances of an agent
    build(rows, settings, table=None) -> {"behaviour": {"held_out", "packaged"}, "session": ...} for the report
    answered(rows, spec) -> the rows calibration reads: answered agents and humans of its sources, left_out apart

A percent says a probability, so of the sessions shown at 90% about 90% must be right (D34). The behaviour map is an
isotonic fit (pool-adjacent-violators) of "an agent acted" on the behaviour score (confidence.score), each class
weighted alike so that the chance reads as if humans and agents were equally common, as the session percent assumes.
Sessions with the same score are one step of the fit. A block's chance is then shrunk towards even by prior_count
sessions of each class (a block of few sessions says little; the ends never read 0 or 1), and the blocks are pooled
again where that broke the order.

check() reads a chance against what the sessions were, both classes weighted alike: per bin of predicted chance, how
many sessions, how many agents, the mean predicted and the actual share of agents; and the Brier score (the mean
squared gap between chance and answer; 0 is perfect, 0.25 is a coin), weighted alike and as counted. build() checks
the behaviour map on each group held out of its fit (fitted again on the others: a data set, or a person where the
data set names one), the packaged map on all of them, and the session percent (every layer together) on every
session with an answer; weak answers are left out.
"""
from agentcake.detect import confidence
from agentcake.units import PERCENT

AGENT, HUMAN = "agent", "human"
AGENT_WEIGHT, HUMAN_WEIGHT, AGENTS, HUMANS, UPPER = range(5)  # protocol: a block's two weights, two counts, top
COUNTS = (AGENT_WEIGHT, HUMAN_WEIGHT, AGENTS, HUMANS)  # what pooling adds up


def fit(points, prior_count):
    """points: [(score, is_agent)]. Blocks [[upper score, chance]] of the balanced isotonic fit, shrunk (see above)."""
    agents = sum(1 for _, is_agent in points if is_agent)
    humans = len(points) - agents
    if not agents or not humans:
        return []
    weight = {True: 1 / agents, False: 1 / humans}  # each class weighs 1 in all

    def balanced(block):
        return block[AGENT_WEIGHT] / (block[AGENT_WEIGHT] + block[HUMAN_WEIGHT])

    def shrunk(block):
        return _shrink(block[AGENTS], block[HUMANS], agents, humans, prior_count)

    tied = {}  # sessions with the same score are one step of the fit: a block never ends inside a tie
    for value, is_agent in points:
        step = tied.setdefault(value, [0.0, 0.0, 0, 0, value])
        step[AGENT_WEIGHT if is_agent else HUMAN_WEIGHT] += weight[is_agent]
        step[AGENTS if is_agent else HUMANS] += 1
    blocks = []
    for value in sorted(tied):
        blocks.append(tied[value])
        _pool(blocks, balanced)
    repaired = []
    for block in blocks:
        repaired.append(list(block))
        _pool(repaired, shrunk)
    return [[block[UPPER], shrunk(block)] for block in repaired]


def check(pairs, bins):
    """pairs: [(chance of an agent, is_agent)]. Reliability per bin and the Brier score (see the module docstring)."""
    agents = sum(1 for _, is_agent in pairs if is_agent)
    humans = len(pairs) - agents
    if not agents or not humans:
        return {"bins": [], "brier": None, "brier_natural": None, "sessions": len(pairs)}
    weight = {True: 1 / agents, False: 1 / humans}
    out = []
    for low, high in bins:
        inside = [(p, a) for p, a in pairs if low <= p < high or (high >= 1 and p == 1)]
        if not inside:
            continue
        total = sum(weight[a] for _, a in inside)
        out.append({"from": low, "to": high, "sessions": len(inside), "agents": sum(1 for _, a in inside if a),
                    "predicted": sum(weight[a] * p for p, a in inside) / total,
                    "actual": sum(weight[a] for _, a in inside if a) / total})
    gaps = [(weight[a], (p - a) * (p - a)) for p, a in pairs]
    return {"bins": out, "brier": sum(w * g for w, g in gaps) / sum(w for w, _ in gaps),
            "brier_natural": sum(g for _, g in gaps) / len(gaps), "sessions": len(pairs)}


def build(rows, settings, table=None):
    """rows: sessions.row()'s of the data sets settings "calibration.sources" names (see the module docstring)."""
    spec, table = settings["calibration"], table or confidence.load_table()
    limit = table["behaviour"]["score_limit"]
    judged = answered(rows, spec)
    scored = []
    for r in judged:
        behaviour = r["evidence"].get("behavior") or {}
        if behaviour.get("verdict") not in (None, "too_little_data") and behaviour.get("segments"):
            scored.append((_fold(r), confidence.score(confidence.agent_part(behaviour, r["class"]), limit),
                           r["truth"]["class"] == AGENT))
    held = []
    for fold in sorted({f for f, _, _ in scored}):
        blocks = fit([(s, a) for f, s, a in scored if f != fold], spec["prior_count"])
        held += [(_chance(blocks, s), a) for f, s, a in scored if f == fold and blocks]
    packaged = table["behaviour"]["blocks"]
    session = [(_agent_chance(r), r["truth"]["class"] == AGENT) for r in judged if r.get("percent") is not None]
    return {"behaviour": {"held_out": check(held, spec["bins"]),
                          "packaged": check([(_chance(packaged, s), a) for _, s, a in scored], spec["bins"]),
                          "folds": sorted({f for f, _, _ in scored})},
            "session": check(session, spec["bins"])}


def answered(rows, spec):
    """The rows of spec "sources" with a certain answer, an agent or a human, without the labels spec "left_out"
    names for their source (the automation we made to look human: eval.json "calibration")."""
    left_out = spec.get("left_out") or {}
    return [r for source in spec["sources"] for r in rows.get(source, [])
            if r["truth"].get("class") in (AGENT, HUMAN) and not r["truth"].get("weak")
            and r["truth"].get("label") not in left_out.get(source, ())]


def _fold(row):
    """What a session is held out with: the person when its data set says (S9.2's PostHog set, the site owner's
    accounts as one), else its data set."""
    return f"{row['source']} / {row['holdout']}" if row.get("holdout") else row["source"]


def _agent_chance(row):
    """The session percent as the chance of an agent: a Human's percent (and a thin one's, D39) is a human's."""
    chance = row["percent"] / PERCENT
    return 1 - chance if row["class"] in confidence.SHOWN_AS_HUMAN else chance


def _chance(blocks, value):
    for upper, chance in blocks:
        if value <= upper:
            return chance
    return blocks[-1][1]


def _shrink(agents, humans, all_agents, all_humans, prior_count):
    """A block's chance of an agent with prior_count sessions of each class added (classes weighted alike)."""
    agent_rate = (agents + prior_count) / (all_agents + 2 * prior_count)  # protocol: one prior per class, two in all
    human_rate = (humans + prior_count) / (all_humans + 2 * prior_count)  # protocol: as above
    return agent_rate / (agent_rate + human_rate)


def _pool(blocks, chance_of):
    """Merge the last block into the one before while it breaks the non-decreasing order (pool-adjacent-violators)."""
    while len(blocks) > 1:
        last = blocks.pop()
        before = blocks[-1]
        if chance_of(before) < chance_of(last):
            blocks.append(last)
            return
        for i in COUNTS:
            before[i] += last[i]
        before[UPPER] = last[UPPER]
