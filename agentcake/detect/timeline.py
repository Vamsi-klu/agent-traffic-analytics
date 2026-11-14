"""Who did each action of a session, the human and agent shares by action, and the hand-offs (plan step S3.7).

Part of the behaviour layer. Input: a session's events in the raw-event format (segment.py; rrweb_events.py
rebuilds it from rrweb recordings), each a dict with "t" (ms) and "ty"; mousemoves carry "cx", "cy". Output of
build(events): {"actions", "evidence", "runs", "shares", "handoffs", "marks", "checks"}:
- actions: [{"kind": "click" | "input", "t", "first", "start", "features", "p", "who"}], in time order. t is when
  the action happened (for typing, its last input); first is its own first event (the click, the first input);
  start is where the activity leading up to it began: the input events since the previous action, back to the last
  pause longer than approach_pause_ms (first when there is none). p is the smoothed chance that an agent did it;
  who is "agent", "human" or "unsure" by the labels' band.
- runs: consecutive actions with the same who, [{"who", "start", "end", "n", "p"}]: start is when the run's actor
  began, end its last action's t, p their mean p. A human (or unsure) run begins where its first action's activity
  began; an agent run with its first action's own first event: the judge calls an action an agent's when nothing
  led up to it (no approach, a jump to the target), so the activity before it belongs to whoever acted before.
- evidence: the scored stretches that are not actions (see build()), with their p and who.
- shares: {"human", "agent", "unsure"}, each a share of the actions (all "unsure" when there is none).
- handoffs: [{"t", "from", "to", "after"}]: where a decided run follows a run of the other actor (unsure runs in
  between are skipped). t is the start of the new actor's first action, after the end of the previous actor's run.
- marks: the turn spans build() was given (see below), [{"marker", "from", "to", ...}].
- checks: the stretches of the behaviour model's session-level checks build() was given, [{"check", "from", "to"}].

An agent product's indicator (markers.turn_spans: cake.js's watch, or the recorder's check) says when its agent was
working. build(..., turns=spans) gives every step inside a span to the agent whatever its score (who "agent", p 1,
"marker": the span's mark): the product said so at that moment, which no reading of the input can. The steps outside
are judged by the model as before, but smoothed apart in the stretches between the spans, so that the agent's lit
actions do not pull the actions next to them its way: once an indicator goes off, what follows is judged on its own
evidence (an indicator's absence is no evidence of a human: other agents draw none). Whatever the page saw while the
indicator was lit is the agent's, so an agent run that begins inside a span begins at the first input after the
indicator lit (the agent may scroll or move for a while before its first click), and a span in which the page saw
input but no action becomes one step of the agent's ("turn", at that first input; evidence, not an action, so the
shares do not count it). Hand-offs stay where the runs change sides, at the new side's first input or action, which is
what GOAL A5 measures against; the indicator's own moment is seconds away from it (it lights while the agent takes its
first screenshot and thinks, and goes off before the person has reached the page), so a hand-off next to a span
carries that moment beside it: "marker": {"id", "t"}, when the indicator lit (to the agent) or went off (from the
agent).

The behaviour model's session-level checks (model.py: the typing rhythm, the pointer's move rate, teleport clicks) read
the session as a whole, so no action's own score shows them; each says which stretch its evidence covers, and
build(..., checks=spans) gives the steps inside that stretch to the agent the same way ("check": the check's name
instead of a marker). They are not an indicator: they make no marks, no "turn" step and no lit or off moment.

The method is cake 0.3.4's per-action judge (its cake.py: rr_actions, p_agent, hmm_smooth; kept as
tests/judge_0_3_4.py, which tests/test_timeline.py checks this module against), which research note 12 found the most
accurate on real mixed replays (conclusion 4). It is read from the raw-event format
instead of rrweb, with the same arithmetic: on the same input it gives 0.3.4's numbers, quirks included (an input
merged into the previous one moves that action's time, not the start of the next pause). Two changes, both to stop
a missing signal from deciding (research note 12's missing variant): an action with no pointer position before it
gets no pointer evidence (no_pointer_no_evidence; false gives 0.3.4's scores), and scrolls and pointer movement,
which 0.3.4 never scored, enter the smoothing as evidence when they carry some (build()'s evidence), so a stretch
with no click or typing can still show who was there. Added here as well: each action's first event and approach
start, the runs' start and mean p, and the hand-offs. smooth() and label() are shared with the session verdict
(model.py). Parameters: agentcake/data/behavior_model.json ("timeline"; "min_actions" for model.py). A click no
mouse made gets no pointer evidence either (job borrow-rules B3, after bot-signal's isPointerClick, MIT,
github.com/okasi/bot-signal 25a4e7b0159f; no code copied).
"""
import bisect
import math

from agentcake import datafiles
from agentcake.detect import features as behaviour_features, segment
from agentcake.units import MS_PER_S

PARAMS_FILE = "data/behavior_model.json"
WHO = ("human", "agent", "unsure")
CLICK = "click"
ACTION_KINDS = (CLICK, "input")
NO_POINTER_FEATURES = ("no_move_act", "straight")  # what an empty pointer window would otherwise count as evidence
TURN = "turn"  # a step of the agent's: input while its indicator was lit, with no action (see build())


def load_params():
    """All parameters of the behaviour model (agentcake/data/behavior_model.json), read once. Shared: copy before
    changing."""
    return datafiles.load(PARAMS_FILE)


def build(events, params=None, session_start=None, evidence=(), turns=(), checks=()):
    """The timeline of one session (see the module docstring).

    params: the whole behavior_model.json (default: the packaged one). session_start: when the session began
    (ms, like the events' t), from which the first action's pause is counted; default: its first event.
    evidence: scored stretches that are not actions (model.py: scrolls and pointer movement that carry evidence),
    each {"kind", "t", "first", "start", "score"}. They are smoothed in time order with the actions and shape the
    runs and hand-offs, but the shares count actions only. turns: the spans in which an agent product's indicator
    said its agent was working (markers.turn_spans), each {"marker", "from", "to"} in ms. checks: the stretches the
    behaviour model's session-level checks cover, each {"check", "from", "to"} in ms (see the module docstring).
    """
    p = (params or load_params())["timeline"]
    acts = actions(events, params, session_start)
    for action in acts:
        action["score"] = p_agent(action["features"], params)
    spans = sorted(turns, key=lambda span: span["from"])
    checked = sorted((dict(check) for check in checks), key=lambda span: span["from"])
    inputs = sorted(e["t"] for e in events if e.get("ty") in segment.INPUT_TYPES) if spans else []
    steps = acts + [dict(stretch) for stretch in evidence]
    steps = sorted(steps + _quiet_turns(spans, steps, inputs), key=lambda step: step["t"])
    for span, group in _by_turn(steps, sorted(spans + checked, key=lambda span: span["from"])):
        if span is not None:
            for step in group:
                step.update(p=1.0, who="agent", **({"marker": span["marker"]} if "marker" in span else
                                                   {"check": span["check"]}))
            continue
        for step, probability in zip(group, smooth([step["score"] for step in group], p["hmm"])):
            step["p"] = probability
            step["who"] = label(probability, p["labels"])
    runs_ = runs(steps, spans)
    _start_lit_runs(runs_, inputs)
    return {"actions": [s for s in steps if s["kind"] in ACTION_KINDS],
            "evidence": [s for s in steps if s["kind"] not in ACTION_KINDS], "runs": runs_,
            "shares": shares([a["who"] for a in acts]), "handoffs": handoffs(runs_), "marks": spans,
            "checks": checked}


def _by_turn(steps, spans):
    """The steps in time order, cut into groups at every span's start and end: (span, its steps) for the steps inside
    one, (None, steps) for each stretch between spans. A step inside overlapping spans goes with the last to start."""
    groups, current, key = [], [], None
    starts = [span["from"] for span in spans]
    for step in steps:
        index = bisect.bisect_right(starts, step["t"]) - 1
        inside = next((i for i in range(index, -1, -1) if spans[i]["from"] <= step["t"] <= spans[i]["to"]), None)
        step_key = ("in", inside) if inside is not None else ("between", index)
        if step_key != key and current:
            groups.append((key, current))
            current = []
        key = step_key
        current.append(step)
    if current:
        groups.append((key, current))
    return [(spans[k[1]] if k[0] == "in" else None, group) for k, group in groups]


def _quiet_turns(spans, steps, times):
    """A "turn" step at the first input inside each span that holds input but no step: the agent acted there (a move,
    a scroll) without a click or typing, which only the indicator shows. times: the input events' times, in order."""
    out = []
    for span in spans:
        if any(span["from"] <= step["t"] <= span["to"] for step in steps):
            continue
        first = bisect.bisect_left(times, span["from"])
        if first < len(times) and times[first] <= span["to"]:
            t = times[first]
            out.append({"kind": TURN, "t": t, "first": t, "start": t, "score": 1.0})
    return out


def _start_lit_runs(runs_, times):
    """An agent run that begins inside a turn span begins at the first input the page saw after the span lit (its
    "lit" moment), when that came before the run's first step: the agent's scrolls and moves are its own too. times:
    the input events' times, in order."""
    for run in runs_:
        if run["who"] != "agent" or "lit" not in run:
            continue
        first = bisect.bisect_left(times, run["lit"]["t"])
        if first < len(times) and times[first] < run["start"]:
            run["start"] = times[first]


def actions(events, params=None, session_start=None):
    """0.3.4's actions: each click, and each input burst (inputs less than input_merge_ms apart), with features.

    Returns [{"kind", "t", "start", "features"}]; features as in 0.3.4's rr_actions (see behavior_model.json), plus
    by_mouse: 0.0 for a click the keyboard, a finger or a pen made (features.mouse_click(); job borrow-rules B3),
    whose pointer approach p_agent() does not read, else 1.0.
    """
    p = (params or load_params())["timeline"]
    events = sorted(events, key=lambda e: e["t"])
    if session_start is None:
        session_start = events[0]["t"] if events else 0
    by_mouse = {id(e) for e in behaviour_features.mouse_clicks(events)}
    moves = _Moves()
    acts, leading_up, t_prev = [], [], session_start
    for e in events:
        kind = e.get("ty")
        if kind == "mousemove":
            moves.add(e)
        if kind == "input" and acts and acts[-1]["kind"] == "input" and e["t"] - acts[-1]["t"] < p["input_merge_ms"]:
            acts[-1]["t"] = e["t"]
            leading_up = []
        elif kind in ACTION_KINDS:
            made_by_mouse = kind != CLICK or id(e) in by_mouse
            acts.append({"kind": kind, "t": e["t"], "first": e["t"], "start": _activity_start(e["t"], leading_up, p),
                         "features": dict(_features(e["t"], t_prev, moves, p), by_mouse=float(made_by_mouse))})
            t_prev, leading_up = e["t"], []
        elif kind in segment.INPUT_TYPES:
            leading_up.append(e["t"])
    return acts


def p_agent(features, params=None):
    """0.3.4's logistic score of one action: the chance an agent did it, before smoothing.

    With no_pointer_no_evidence, an action with no pointer position in its window gets nothing from the two pointer
    features that would read the empty window as a jump (no_move_act) and as a straight path (straight): the
    pointer may not have moved at all, or a key made the click. An agent leaves one position, where it jumped to.
    The same goes for a click no mouse made (by_mouse 0: job borrow-rules B3): the browser's one move at a tapped spot
    is no jump.
    """
    p = (params or load_params())["timeline"]
    no_pointer = features["moves_before_act"] == 0 or not features.get("by_mouse", 1.0)
    if p["no_pointer_no_evidence"] and no_pointer:
        features = {**features, **dict.fromkeys(NO_POINTER_FEATURES, 0.0)}
    z = p["bias"] + sum(weight * features[name] for name, weight in p["weights"].items())
    limit = p["logit_limit"]
    return 1 / (1 + math.exp(-max(-limit, min(limit, z))))


def smooth(scores, hmm):
    """Two-state hidden Markov smoothing of per-segment agent scores: the posterior chance of "agent" for each.

    hmm: {"switch", "prior", "temper", "clamp"}. Forward-backward with tempered emissions, normalised at every step
    (the lab's labcore.forward_backward; with clamp 0 and prior 0.5 it is 0.3.4's hmm_smooth).
    """
    n = len(scores)
    if not n:
        return []
    low, high = hmm["clamp"], 1 - hmm["clamp"]
    emit = [(max(low, min(high, s)) ** hmm["temper"], (1 - max(low, min(high, s))) ** hmm["temper"])
            for s in scores]  # (agent, human)
    stay, switch = 1 - hmm["switch"], hmm["switch"]
    forward = [_normalised((hmm["prior"] * emit[0][0], (1 - hmm["prior"]) * emit[0][1]))]
    for t in range(1, n):
        agent, human = forward[-1]
        forward.append(_normalised(((agent * stay + human * switch) * emit[t][0],
                                    (agent * switch + human * stay) * emit[t][1])))
    backward = [(1.0, 1.0)] * n
    for t in reversed(range(n - 1)):
        (e_agent, e_human), (b_agent, b_human) = emit[t + 1], backward[t + 1]
        backward[t] = _normalised((stay * e_agent * b_agent + switch * e_human * b_human,
                                   switch * e_agent * b_agent + stay * e_human * b_human))
    posteriors = []
    for (f_agent, f_human), (b_agent, b_human) in zip(forward, backward):
        both = f_agent * b_agent + f_human * b_human
        posteriors.append(f_agent * b_agent / both if both else 0.0)
    return posteriors


def label(probability, labels):
    """"agent" at or above labels["agent_min"], "human" at or below labels["human_max"], else "unsure"."""
    if probability >= labels["agent_min"]:
        return "agent"
    return "human" if probability <= labels["human_max"] else "unsure"


def runs(acts, spans=()):
    """Consecutive actions with the same who, as runs (see the module docstring). A run that begins or ends with a
    step inside a turn span (spans: build()'s turns) notes when that span lit ("lit") or went off ("off")."""
    out = []
    for action in acts:
        if out and out[-1]["who"] == action["who"]:
            run = out[-1]
            run["end"], run["n"], run["_p"], run["_last"] = action["t"], run["n"] + 1, run["_p"] + [action["p"]], action
        else:
            start = action["first"] if action["who"] == "agent" else action["start"]
            out.append({"who": action["who"], "start": start, "end": action["t"], "n": 1, "_p": [action["p"]],
                        "_first": action, "_last": action})
    for run in out:
        values = run.pop("_p")
        run["p"] = sum(values) / len(values)
        for edge, moment, key in (("_first", "from", "lit"), ("_last", "to", "off")):
            step = run.pop(edge)
            span = next((s for s in spans if s["marker"] == step.get("marker") and s["from"] <= step["t"] <= s["to"]),
                        None) if "marker" in step else None
            if span is not None:
                run[key] = {"id": span["marker"], "t": span[moment]}
    return out


def shares(labels):
    """Share of the actions per who; no action at all is all unsure."""
    if not labels:
        return {"human": 0.0, "agent": 0.0, "unsure": 1.0}
    return {who: labels.count(who) / len(labels) for who in WHO}


def handoffs(runs_):
    """Where a decided run follows a decided run of the other actor; unsure runs in between are skipped. Next to a
    turn span, the indicator's moment: when it lit, for a hand-off to an agent run that began inside the span, or
    when it went off, for one from an agent run that ended inside it."""
    out, previous = [], None
    for run in runs_:
        if run["who"] == "unsure":
            continue
        if previous is not None and run["who"] != previous["who"]:
            handoff = {"t": run["start"], "from": previous["who"], "to": run["who"], "after": previous["end"]}
            moment = run.get("lit") if run["who"] == "agent" else previous.get("off")
            if moment:
                handoff["marker"] = moment
            out.append(handoff)
        previous = run
    return out


class _Moves:
    """The mousemoves seen so far, in time order, for windows that end at the current event."""

    def __init__(self):
        self.times, self.points = [], []

    def add(self, e):
        self.times.append(e["t"])
        self.points.append((e.get("cx") or 0, e.get("cy") or 0))

    def since(self, t_from):
        """Index of the first move at or after t_from."""
        return bisect.bisect_left(self.times, t_from)


def _features(t, t_prev, moves, p):
    """0.3.4's rr_actions' five features of an action at t, the previous one at t_prev (moves up to t seen)."""
    caps = p["caps"]
    window = moves.points[moves.since(t - p["window_ms"]):]
    path = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(window, window[1:]))
    chord = math.hypot(window[-1][0] - window[0][0], window[-1][1] - window[0][1]) if len(window) > 1 else 0
    span = max(p["min_span_s"], (t - t_prev) / MS_PER_S)
    moved = len(moves.times) - moves.since(t_prev)
    return {"moves_per_s": min(moved / span, caps["moves_per_s"]),
            "moves_before_act": min(len(window), caps["moves_before_act"]),
            "straight": chord / path if path > 0 and len(window) >= p["min_straight_moves"] else 1.0,
            "pause_s": min((t - t_prev) / MS_PER_S, caps["pause_s"]),
            "no_move_act": 1.0 if len(window) <= 1 else 0.0}


def _activity_start(first, earlier, p):
    """The first of the input events before an action (since the previous one) that lead up to it without a pause
    longer than approach_pause_ms; first when none does."""
    start = first
    for t_event in reversed(earlier):
        if start - t_event > p["approach_pause_ms"]:
            break
        start = t_event
    return start


def _normalised(pair):
    total = pair[0] + pair[1]
    return (pair[0] / total, pair[1] / total) if total else pair
