"""Is the whole session an agent's? The behaviour model's verdict, and the one result the verdict step reads
(the verdict combines it with the other layers).

judge_session(events, raw_input=True, touch=False, session_start=None, params=None, turns=()) is the interface for
the verdict. Input: one session's events in the raw-event format (segment.py; for an rrweb-only recording, rebuild them with
rrweb_events.events_from_rrweb() and pass raw_input=False). touch: the device is a phone or a tablet. turns: when an
agent product's indicator said its agent was working (markers.turn_spans), which the timeline gives to the agent; the
session's own verdict does not read them. Nothing is sent anywhere: it is plain arithmetic on the events. Returns:

    {"verdict": "agent" | "human" | "unsure" | "too_little_data",
     "confidence": share of the action segments whose own label is the verdict (None when too little data),
     "basis": what decided: "rules" (the segments' majority), "active_move_rate", "teleport_clicks",
              "typing_cadence" (fallback),
     "evidence": {"agent_share", "human_share", "unsure_share", "active_move_rate", "mouse_pointer",
                  "teleport_click_share", "typing_cadence": cadence.judge() (None: no evidence),
                  "rule_hits": {rule id: segments it fired in},
                  "agent_kinds": the kinds of the agent rules that fired, "agent_observations": segments where one
                  fired, and "one_kind": the only kind behind an agent verdict that was not corroborated}
                 or {"reason": "touch" | "few_actions"},
     "n_actions": action segments (segment.actions), "raw_input": as given,
     "segments": [{"start", "end", "act_t", "kind", "p_rules", "p", "who", "rules"}] (empty when too little data),
     "timeline": timeline.build(...) (who did each action, the scroll and movement stretches that carry evidence,
                 shares by action, hand-offs, the turn spans it was given), or None}

The verdict is the main model of our study of PostHog replays, in its missing-data variant: the lab's readable rules score each
action segment (features.py; without raw input the 8 features rrweb cannot see are "no data" and fire nothing),
a two-state HMM smooths the scores over the session, and the session is an agent's when at least min_agent_actions of
its segments are an agent's on their own evidence (labelled agent, at agent_min, and an agent rule fired in them) or
when the fallback fires:
a mouse drives the pointer (mouse_pointer()), it moved at least min_moves times and it moves fewer than
active_rate_below times a second while it moves, or more than teleport_share_above of the clicks a mouse made come
right after a jump, or, with raw input, the class isHumanCadence gives the session's typing ends at bot (cadence.py:
the typing as a whole, which no single typing segment shows). A pointer that hardly moved gives no rate at all: there
is no movement to measure, which says
nothing about who held it (after agent-detector's "missing is not negative"); nor has a click
the keyboard, a finger or a pen made an approach to read. Otherwise the session is a human's when any of its
segments is, and unsure when none is either: segments nobody can tell count for neither side (human + unknown is human, agent + unknown is agent, human + agent + unknown is agent). Without hard evidence
(a device event a script dispatched: features.py untrusted), an agent verdict also needs evidence of two independent
kinds (each rule's kind: how the pointer reaches its clicks, where clicks land, how it moves, typing, the input events
themselves, scrolling, page focus; after agent-detector
and HABITS): one ambiguous click approach that the HMM spreads over a short session is how people were taken for
agents. An rrweb-only recording can show two kinds at most, so there evidence on two actions (segments where an agent
rule fired, and the session's pointer movement when it moves too seldom) stands in for the second kind. An
uncorroborated agent verdict is unsure, and the evidence names its one kind ("one_kind"). Phones, tablets and sessions
with fewer than min_actions action segments are too little data and no model runs (threshold A8). Automation that looks human
(Playwright made to move like a hand) is the environment layer's to name; behaviour does not overrule it.
The shares and hand-offs come from
timeline.py (0.3.4's per-action judge, the most accurate on mixed replays), which also reads the scroll and movement
segments that carry evidence (movement_evidence()), so a stretch without clicks or typing still shows who was there.
A session-level check in the basis reads the session as a whole, so no action's own score shows it: the stretch its
evidence covers (checked_stretches(): the typing window, each teleport click, the run of movements where fast arrivals
gather, and all the pointer movement when no segment located the agent's part) goes to the agent on the timeline, as
a lit indicator's span does, and a hand-off, and so a Human + agent session, needs a human's evidence outside it (no
evidence that a human was there, no Human + agent).

Ported from our own code with the same arithmetic: the rules and the HMM from the behaviour lab's
labcore.py (rule_score, forward_backward; 2026-11-11), the fallback from
cake-data/compare_models.py (active_rate, choudhary; 2026-11-11), the decision from cake-ph-eval/phcore.py
(rules_hmm with rr_mode, all_models' main_rr; 2026-11-12). Parameters: agentcake/data/behavior_model.json.
Two ideas come from other projects' rules, MIT, no code copied: a pointer that hardly moved
gives no move rate (agent-detector, github.com/doubleagent-so/agent-detector a523214c3b67: "missing is not
negative"), and only a mouse's clicks can be teleports (bot-signal, github.com/okasi/bot-signal 25a4e7b0159f:
isPointerClick).
"""
import bisect
import math
import operator

from agentcake.detect import arrival, cadence, clicks, features, timeline
from agentcake.units import MS_PER_S

OPERATORS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}
MISSING_VALUE = 3  # protocol: index of a condition's optional "value when the feature has no data"
GLIDES = "pointer_glides"  # the movement evidence's id in a step's rules
ACTIVE_RATE = "active_move_rate"  # the fallback basis read from the whole session's pointer movement
TYPING = "typing_cadence"  # the fallback basis read from the whole session's typing (cadence.py)
TELEPORTS = "teleport_clicks"  # the fallback basis read from the clicks right after a pointer jump
ARRIVALS = "fast_arrivals"  # the fallback basis read from how the pointer arrives at its presses (arrival.py)
RULES = "rules"  # the basis of enough segments that are an agent's on their own evidence
MOUSE = clicks.MOUSE
NOT_A_MOUSE = clicks.TOUCH_OR_PEN
MOUSE_EVENTS = frozenset({"mousemove", "mousedown", "mouseup", "click", "dblclick", "contextmenu"})
load_params = timeline.load_params


def judge_session(events, raw_input=True, touch=False, session_start=None, params=None, turns=()):
    """The behaviour layer's result for one session (see the module docstring)."""
    params = params or load_params()
    events = sorted(events, key=lambda e: e["t"])
    if touch:
        return too_little_data("touch", None, raw_input)
    segments = features.session_features(events, raw_input=raw_input)
    if len(segments) < params["min_actions"]:
        return too_little_data("few_actions", len(segments), raw_input)
    decided = decide_segments(segments, events, raw_input, params)
    scored, smoothed, labels = decided["scored"], decided["smoothed"], decided["labels"]
    verdict, basis, evidence = decided["verdict"], decided["basis"], decided["evidence"]
    return {"verdict": verdict, "confidence": evidence[verdict + "_share"], "basis": basis, "evidence": evidence,
            "n_actions": len(segments), "raw_input": raw_input,
            "segments": [{"start": seg["start"], "end": seg["end"], "act_t": seg["act_t"], "kind": seg["kind"],
                          "p_rules": p_rules, "p": p, "who": who, "rules": fired}
                         for seg, (p_rules, fired), p, who in zip(segments, scored, smoothed, labels)],
            "timeline": timeline.build(events, params, session_start, movement_evidence(segments, params), turns,
                                       checked_stretches(basis, evidence, events, params))}


def decide_segments(segments, events, raw_input=True, params=None):
    """The session's verdict from its measured segments (features.session_features) and its events: each segment
    scored by the rules, smoothed and labelled, and the decision; no timeline. judge_session() is this plus the
    timeline; the evaluation calls it to judge the same segments under other parameters
    (agentcake/evaluation/heldout.py). Returns {"verdict", "basis", "evidence", "scored", "smoothed", "labels"}."""
    params = params or load_params()
    scored = [rule_score(seg["features"], params) for seg in segments]
    smoothed = timeline.smooth([p for p, _ in scored], params["hmm"])
    labels = [timeline.label(p, params["labels"]) for p in smoothed]
    evidence = _evidence(labels, scored, events, params)
    verdict, basis = _decide(evidence, params, raw_input)
    return {"verdict": verdict, "basis": basis, "evidence": evidence, "scored": scored, "smoothed": smoothed,
            "labels": labels}


def rule_score(feature_values, params=None):
    """(score, ids of the rules that fired) for one segment's features: the logistic of the summed weights."""
    logit, fired = _rule_logit(feature_values, params or load_params())
    return _logistic(logit), fired


def movement_evidence(segments, params=None):
    """The scroll and pointer-movement segments that carry evidence, as timeline steps.

    Each is scored by the rules plus pointer_glides (behavior_model.json, timeline.evidence): when the segment's
    pointer glides like a hand, which no agent we recorded does. A segment where nothing fires (0.5) is left out:
    it says nothing about who was there. None at all when timeline.movement_evidence is false.
    """
    params = params or load_params()
    if not params["timeline"]["movement_evidence"]:
        return []
    settings = params["timeline"]["evidence"]
    steps = []
    for seg in segments:
        if seg["kind"] not in settings["kinds"]:
            continue
        logit, fired = _rule_logit(seg["features"], params)
        rate = active_move_rate([e for e in seg["events"] if e.get("ty") == "mousemove"], params)
        if rate is not None and rate >= params["fallback"]["active_rate_below"]:
            logit += settings["pointer_glides_weight"]
            fired.append(GLIDES)
        if fired:
            steps.append({"kind": seg["kind"], "t": seg["act_t"], "first": seg["act_t"], "start": seg["start"],
                          "score": _logistic(logit), "rules": fired})
    return steps


def active_move_rate(events, params=None):
    """Mousemoves per second, counting only the time inside movement bursts (moves less than burst_gap_ms apart);
    0 when the pointer moved but never in a burst (compare_models.active_rate); None, no data, with fewer than
    min_moves moves."""
    p = (params or load_params())["fallback"]
    times = sorted(e["t"] for e in events if e.get("ty") == "mousemove")
    if len(times) < p["min_moves"]:
        return None
    active_ms = sum(gap for gap in (b - a for a, b in zip(times, times[1:])) if gap < p["burst_gap_ms"])
    return len(times) / max(active_ms / MS_PER_S, p["min_active_s"]) if active_ms > 0 else 0.0


def mouse_pointer(events):
    """Whether a mouse drives the pointer: a pointer event says pointerType "mouse", or none names a pointer type and
    a mouse event fired. A finger or a pen makes the browser fire mouse events too (mousemove, mousedown, mouseup and
    click after a tap, for pages written for a mouse), so once a pointer event says touch or pen, mouse events alone
    are not a mouse's. Without a mouse the active move rate says nothing (experiment 2: touch screens and sessions
    that only scroll and type read as a pointer that never glides)."""
    pointer_types = {e.get("pt") for e in events if e.get("pt")}
    if MOUSE in pointer_types:
        return True
    if pointer_types & NOT_A_MOUSE:
        return False
    return any(e.get("ty") in MOUSE_EVENTS for e in events)


def teleport_click_share(events, params=None):
    """Share of the clicks a mouse made that show an approach of their own (features.approached_clicks(): not the
    keyboard's, a finger's or a pen's, and not a repeat in place of the click before) with no mousemove before
    them, or whose last move (at most click_window_ms before) came after a jump of more than jump_px in less than
    jump_ms; None without such clicks (compare_models.choudhary)."""
    approached = features.approached_clicks(sorted(events, key=lambda e: e["t"]))
    return len(teleport_clicks(events, params)) / len(approached) if approached else None


def teleport_clicks(events, params=None):
    """The times of the clicks teleport_click_share() counts."""
    p = (params or load_params())["fallback"]
    events = sorted(events, key=lambda e: e["t"])
    moves = [e for e in events if e.get("ty") == "mousemove"]
    times = [e["t"] for e in moves]
    out = []
    for click in features.approached_clicks(events):
        seen = bisect.bisect_right(times, click["t"])
        if not seen:
            out.append(click["t"])
            continue
        last = moves[seen - 1]
        before = bisect.bisect_left(times, last["t"])  # moves strictly earlier than the last one
        if click["t"] - last["t"] <= p["click_window_ms"]:
            if not before:
                out.append(click["t"])
            elif last["t"] - times[before - 1] < p["jump_ms"] and _jump(moves[before - 1], last) > p["jump_px"]:
                out.append(click["t"])
    return out


def checked_stretches(basis, evidence, events, params=None):
    """The stretch each session-level check in the basis covers, which the timeline gives to the agent (timeline.py
    checks, after the indicator's turn spans): the typing rhythm its window of keys (cadence.py span), the move rate
    the pointer movement it measured (the first move to the last), a teleport click its own moment, fast arrivals the
    run of movements where they gather (arrival.py span)."""
    out = []
    typing = evidence.get(TYPING)
    if TYPING in basis and typing and typing.get("span"):
        out.append({"check": TYPING, "from": typing["span"][0], "to": typing["span"][1]})
    if TELEPORTS in basis:
        out += [{"check": TELEPORTS, "from": t, "to": t} for t in teleport_clicks(events, params)]
    if ARRIVALS in basis:
        out.append({"check": ARRIVALS, "from": evidence[ARRIVALS]["span"][0], "to": evidence[ARRIVALS]["span"][1]})
    if ACTIVE_RATE in basis and RULES not in basis:  # all the movement: only when nothing located the agent's part
        moves = sorted(e["t"] for e in events if e.get("ty") == "mousemove")
        out.append({"check": ACTIVE_RATE, "from": moves[0], "to": moves[-1]})
    return out


def _rule_logit(feature_values, params):
    logit, fired = 0.0, []
    for rule in params["rules"]["list"]:
        if all(_holds(condition, feature_values) for condition in rule["all"]):
            logit += rule["weight"]
            fired.append(rule["id"])
    return logit, fired


def _logistic(logit):
    return 1 / (1 + math.exp(-logit))


def _holds(condition, feature_values):
    name, op, value = condition[:MISSING_VALUE]
    actual = feature_values.get(name)
    if actual is None:
        if len(condition) <= MISSING_VALUE:
            return False
        actual = condition[MISSING_VALUE]
    return OPERATORS[op](actual, value)


def _evidence(labels, scored, events, params):
    n = len(labels)
    hits = {}
    for _, fired in scored:
        for rule_id in fired:
            hits[rule_id] = hits.get(rule_id, 0) + 1
    agent_rules = {rule["id"]: rule["kind"] for rule in params["rules"]["list"] if rule["weight"] > 0}
    return {"agent_share": labels.count("agent") / n, "human_share": labels.count("human") / n,
            "agent_actions": sum(1 for label, (_, fired) in zip(labels, scored)
                                 if label == "agent" and any(r in agent_rules for r in fired)),
            "unsure_share": labels.count("unsure") / n, "active_move_rate": active_move_rate(events, params),
            "mouse_pointer": mouse_pointer(events), "teleport_click_share": teleport_click_share(events, params),
            TYPING: cadence.judge(events, params["cadence"]), ARRIVALS: arrival.judge(events, params["arrival"]),
            "rule_hits": hits, "agent_kinds": sorted({agent_rules[r] for r in hits if r in agent_rules}),
            "agent_observations": sum(1 for _, fired in scored if any(r in agent_rules for r in fired))}


def _decide(evidence, params, raw_input=True):
    """(verdict, basis): an agent when its part of the session meets the bar (at least min_agent_actions segments are
    an agent's on their own evidence, or the fallback fires) and is corroborated (_corroborated); else a human when
    any segment is a human's; else unsure. Segments nobody can tell count for neither side (human + unknown
    is human). The smoothing labels a strong action's neighbours too, so the bar counts the actions whose own rules said
    agent: one action never makes an agent of a session, whatever it pulls along."""
    fallback = params["fallback"]
    basis = ["rules"] if evidence["agent_actions"] >= params["session"]["min_agent_actions"] else []
    rate = evidence["active_move_rate"]
    if evidence["mouse_pointer"] and rate is not None and rate < fallback["active_rate_below"]:
        basis.append("active_move_rate")
    teleports = evidence["teleport_click_share"]
    if teleports is not None and teleports > fallback["teleport_share_above"]:
        basis.append(TELEPORTS)
    typing = evidence[TYPING]
    if raw_input and typing and typing["class"] == cadence.BOT:
        basis.append(TYPING)
    arrivals = evidence[ARRIVALS]
    if raw_input and evidence["mouse_pointer"] and arrivals and arrivals["holds"]:
        basis.append(ARRIVALS)
    if basis:
        kinds = _kinds(evidence, basis, params)
        if _corroborated(evidence, basis, kinds, params, raw_input):
            return "agent", basis
        evidence["one_kind"] = kinds[0] if kinds else None
        return "unsure", []
    if evidence["human_share"] > 0:
        return "human", ["rules"]
    return "unsure", []


def _kinds(evidence, basis, params):
    """The kinds of evidence behind an agent verdict: the agent rules that fired and the fallbacks in the basis."""
    fallback_kinds = params["fallback"]["kinds"]
    return sorted(set(evidence["agent_kinds"]) | {fallback_kinds[b] for b in basis if b in fallback_kinds})


def _corroborated(evidence, basis, kinds, params, raw_input):
    """Whether an agent verdict stands (session.corroboration): a hard rule fired, or evidence of min_kinds kinds,
    or, without raw input, evidence on enough actions."""
    rule = params["session"]["corroboration"]
    if any(evidence["rule_hits"].get(rule_id) for rule_id in rule["hard_rules"]):
        return True
    if len(kinds) >= rule["min_kinds"]:
        return True
    # a teleport click lies in a click segment the rules already read; the move rate spans the whole session
    observations = evidence["agent_observations"] + (ACTIVE_RATE in basis)
    return not raw_input and observations >= rule["min_observations_without_raw_input"]


def too_little_data(reason, n_actions, raw_input):
    """judge_session()'s result when it cannot judge ("touch" or "few_actions"): its keys, no segments, no timeline.
    behavior.run() gives the same without running the model."""
    return {"verdict": "too_little_data", "confidence": None, "basis": [], "evidence": {"reason": reason},
            "n_actions": n_actions, "raw_input": raw_input, "segments": [], "timeline": None}


def _jump(a, b):
    return math.hypot(b["cx"] - a["cx"], b["cy"] - a["cy"])
