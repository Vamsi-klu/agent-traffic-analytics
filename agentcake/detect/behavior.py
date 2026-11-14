"""The behaviour layer as the verdict step runs it (S3.4): S3.7's model on a session's events, unless it cannot judge.

    run(raw=None, rrweb=None, touch=False, session_start=None, model=None, params=None, turns=()) -> result
    assistive_signs(raw, settings=None) -> {"keys": n, "pointer_moves": n} or None

run() counts the session's action segments first (segment.actions, the count the model itself uses): a phone or a
tablet, or fewer segments than the model's min_actions (behavior_model.json), is "too little data" (A8) and the model
is not called at all, so a schedule can call run() on every new batch cheaply. Otherwise it returns the model's own
result, model.judge_session()'s dict (see agentcake/detect/model.py); the too-little-data result has the same shape.
raw is the session's events in the raw-event format cake.js sends (segment.py); a recording with only rrweb events
(cake 0.3.x) is rebuilt with rrweb_events.events_from_rrweb() and judged without raw input (research note 12's missing
variant). model: what judges (default model.judge_session; tests pass a stand-in). turns: when an agent product's
indicator said its agent was working (markers.turn_spans), handed to the model's timeline. Nothing leaves this
computer.

assistive_signs() reads keyboard navigation without a pointer (research note 13, sig-088): an assistive tool's way of
moving through a page, which the model can take for an agent's. cake.js sends each key's class, never the key; an
rrweb-only recording has no keys, so it gives no signs. Thresholds: agentcake/data/verdict.json "assistive".
"""
from agentcake import datafiles
from agentcake.detect import model as behavior_model, rrweb_events, segment

SETTINGS_FILE = "data/verdict.json"
KEYDOWN = "keydown"
POINTER_MOVES = frozenset({"mousemove", "pointermove"})


def run(raw=None, rrweb=None, touch=False, session_start=None, model=None, params=None, turns=()):
    """The behaviour layer's result for one session (see the module docstring)."""
    params = params or behavior_model.load_params()
    events, raw_input = _events(raw, rrweb)
    if touch:
        return behavior_model.too_little_data("touch", None, raw_input)
    n_actions = len(segment.actions(events))
    if n_actions < params["min_actions"]:
        return behavior_model.too_little_data("few_actions", n_actions, raw_input)
    judge = model or behavior_model.judge_session
    return judge(events, raw_input=raw_input, touch=False, session_start=session_start, params=params, turns=turns)


def assistive_signs(raw, settings=None):
    """Keyboard navigation without a pointer, as {"keys", "pointer_moves"}; None when the session shows none."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["assistive"]
    events = raw or []
    keys = sum(1 for e in events if e.get("ty") == KEYDOWN and e.get("kc") in rule["key_classes"])
    moves = sum(1 for e in events if e.get("ty") in POINTER_MOVES)
    if keys >= rule["min_keys"] and moves <= rule["max_pointer_moves"]:
        return {"keys": keys, "pointer_moves": moves}
    return None


def _events(raw, rrweb):
    """(events in time order, whether they are raw input) from what the session recorded."""
    if raw:
        return sorted(raw, key=lambda e: e["t"]), True
    return sorted(rrweb_events.events_from_rrweb(rrweb or []), key=lambda e: e["t"]), False
