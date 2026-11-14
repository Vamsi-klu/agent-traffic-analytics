"""How sure a verdict is, as percents: each layer's lean, and the session's chance of being right (the session
page shows a percent for the whole verdict and for each layer).

    annotate(result, evidence, table=None) -> result, with "percent" and, in each layer, "percent" and "leans"
    behaviour_chance(behaviour, cls, table=None) -> the calibrated chance of an agent from the behaviour model, or None
    agent_part(behaviour, cls) -> the behaviour model's segments that chance reads (the fit and agentcake eval too)
    score(segments, limit) -> the behaviour model's segments in one number: the mean log-odds of their scores

A percent says a probability, so it is calibrated: of the sessions shown at 90%, about 90% are right. Each
layer's evidence is turned into a likelihood ratio, and the layers that judged add their log-likelihood ratios
(agent-detector's way), as if humans and agents were equally common: what a percent means on a site
where agents are rare is the scoreboard's precision at 1% and 5% (agentcake/evaluation/scoreboard.py).
- behaviour: score() mapped by an isotonic fit on sessions with known answers, each class weighted alike
  (agentcake/data/calibration.json "behaviour", fitted by the maintainers' calibration script; agentcake eval checks
  it on data sets held out of the fit). In an Agent's and a Human + agent session the agent's own part is scored (the
  question is whether an agent took part, in Agent only sessions too): the segments the model labelled
  agent and those in a stretch a session-level check covers (timeline "checks"), or all of them when there are none.
  When the session's typing ends at bot (cadence.py), which no segment's score shows, its declared strength
  (calibration.json "layers" typing_cadence) is added to the behaviour's log-odds; so is fast_arrivals' when, with
  raw input and a mouse, enough of the pointer's movements arrive at their target without slowing down (arrival.py).
  Only automation made to look human action by action trips that check (no person and no other agent product in our
  data), so the action scores that point to a person are what it imitates and say nothing against an agent then: the
  map's chance counts only when it is above even (explaining away), and the check's strength is added to that.
- name, verify, environment: the strength of what they found (calibration.json "layers"): declared, not fitted, as
  few people in our data show any of it (a hard automation trace or a verified signature reads as near certain).
A layer that found nothing, did not run or saw too little leans nowhere: its percent and leans are None. A layer
leans to the side of its own conclusion, so that the two never point opposite ways on the page (the coordinator,
11/13): the behaviour layer's human, agent or Human + agent (verdict.py's state, from the model's rule), with the
calibrated chance of that side, which falls under 50 when the evidence the map reads disagrees with the rule; only a
behaviour layer without a side (unsure) leans to its chance's. The session's log-likelihood ratios are the same either
way.

The session's percent is the chance its class is right: for Human the chance of a human, and so for the sessions
shown as a Human with thin evidence (not_sure, too_little_data, the user's rule of 11/13), which is often low; for
Agent and Human + agent (class mixed) of an agent; for Bot how its name was checked; an excluded session (no visit)
has none. Each percent is a whole number inside calibration.json "clamp" (1 to 99).
"""
import bisect
import math

from agentcake import datafiles
from agentcake.units import PERCENT

TABLE_FILE = "data/calibration.json"
AGENT, HUMAN, BOT, MIXED, EXCLUDED = "agent", "human", "bot", "mixed", "excluded"
SHOWN_AS_HUMAN = frozenset({HUMAN, "not_sure", "too_little_data"})  # thin evidence is shown as a Human
LEANING = (AGENT, HUMAN)  # the leans that add a likelihood ratio (a bot is neither)
HARD = "hard"  # protocol: env_rules.json strength of a trace that decides alone
TYPING, BOT_TYPING = "typing_cadence", "bot"  # the behaviour's typing check (model.py) and its agent class
ARRIVALS = "fast_arrivals"  # the behaviour's arrival check (model.py, arrival.py)


def load_table():
    return datafiles.load(TABLE_FILE)


def annotate(result, evidence, table=None):
    """The verdict with its percents (see the module docstring); the layers keep their state and why."""
    table = table or load_table()
    layers = {name: dict(state) for name, state in result["layers"].items()}
    leans = {"name": _named(result, layers.get("name"), table), "verify": _verified(layers.get("verify"), table),
             "environment": _environment(result, layers.get("environment"), table),
             "behavior": _behaviour(evidence.get("behavior"), result["class"], table,
                                    (layers.get("behavior") or {}).get("state"))}
    for name, layer in layers.items():
        side, chance = leans.get(name) or (None, None)
        layer["leans"], layer["percent"] = side, _whole(chance, table) if side else None
    return {**result, "layers": layers, "percent": _session_percent(result, leans, table)}


def behaviour_chance(behaviour, cls, table=None):
    """The calibrated chance that an agent acted, from the behaviour model's result; None when it did not judge."""
    if not behaviour or behaviour.get("verdict") in (None, "too_little_data") or not behaviour.get("segments"):
        return None
    calibration = (table or load_table())["behaviour"]
    segments = agent_part(behaviour, cls)
    blocks = calibration["blocks"]
    found = bisect.bisect_left([upper for upper, _ in blocks], score(segments, calibration["score_limit"]))
    return blocks[min(found, len(blocks) - 1)][1]


def agent_part(behaviour, cls):
    """The segments the behaviour's chance reads (see the module docstring): for an Agent or a Human + agent the
    agent's own part, else every segment."""
    segments = behaviour["segments"]
    if cls not in (AGENT, MIXED):
        return segments
    checks = (behaviour.get("timeline") or {}).get("checks") or []
    own = [s for s in segments if s.get("who") == AGENT or any(c["from"] <= s["act_t"] <= c["to"] for c in checks)]
    return own or segments


def score(segments, limit):
    """The mean log-odds of the segments' smoothed scores ("p"), each held inside -limit..limit."""
    odds = [max(-limit, min(limit, _logit(segment["p"]))) for segment in segments]
    return sum(odds) / len(odds)


def _named(result, layer, table):
    state = (layer or {}).get("state")
    if state not in (AGENT, BOT):
        return None
    strength = table["layers"]
    chance = {"verified": strength["verified"], "impersonation": strength["impersonation"]}.get(
        result.get("verification"), strength["self_reported"])
    return state, chance


def _verified(layer, table):
    state = (layer or {}).get("state")
    return (state, table["layers"]["verified"]) if state in (AGENT, BOT) else None


def _environment(result, layer, table):
    state, strength = (layer or {}).get("state"), table["layers"]
    if state == AGENT:
        hard = any(r.get("strength") == HARD and r.get("tone") == AGENT for r in result.get("reasons") or ())
        return AGENT, strength["env_hard"] if hard else strength["env_counted"]
    if state == "unsure":  # soft traces alone: they lean, they do not count
        return AGENT, strength["env_soft_alone"]
    return None


def _behaviour(behaviour, cls, table, state=None):
    chance = behaviour_chance(behaviour, cls, table)
    if chance is None:
        return None
    evidence, raw_input = behaviour.get("evidence") or {}, behaviour.get("raw_input", True)
    typing, arrivals = evidence.get(TYPING), evidence.get(ARRIVALS)
    if raw_input and typing and typing["class"] == BOT_TYPING:
        chance = 1 / (1 + math.exp(-(_logit(chance) + _logit(table["layers"][TYPING]))))
    if raw_input and evidence.get("mouse_pointer") and arrivals and arrivals["holds"]:  # as the model reads it
        chance = 1 / (1 + math.exp(-(max(_logit(chance), 0.0) + _logit(table["layers"][ARRIVALS]))))
    if state == HUMAN:  # the layer's own conclusion is the side: the percent is how sure it is
        return HUMAN, 1 - chance
    if state in (AGENT, MIXED):
        return AGENT, chance
    return (AGENT, chance) if chance >= 1 - chance else (HUMAN, 1 - chance)


def _session_percent(result, leans, table):
    cls = result["class"]
    if cls == EXCLUDED:
        return None
    if cls == BOT:
        checked = [chance for side, chance in (leans[n] or (None, None) for n in ("verify", "name")) if side == BOT]
        return _whole(max(checked) if checked else table["layers"]["self_reported"], table)
    log_odds = sum(_logit(chance if side == AGENT else 1 - chance)
                   for side, chance in (lean for lean in leans.values() if lean) if side in LEANING)
    agent = 1 / (1 + math.exp(-log_odds))
    return _whole(1 - agent if cls in SHOWN_AS_HUMAN else agent, table)


def _whole(chance, table):
    low, high = table["clamp"]
    return round(PERCENT * min(high, max(low, chance)))


def _logit(p):
    p = min(1 - 1e-12, max(1e-12, p))  # protocol: keeps the log finite at 0 and 1
    return math.log(p / (1 - p))
