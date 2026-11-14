"""Cut a session's input into segments: fixed windows, or one segment per action (plan step S3.6).

Part of the behaviour layer. Input: a session's events in the raw-event format of our lab's raw.js (the format
cake.js sends; rrweb_events.py rebuilds it from rrweb recordings), each a dict with at least "t" (epoch ms) and
"ty" (the DOM event type), sorted by "t". Output: segments as dicts holding their events; features.py measures them.

Ported unchanged from our own lab code: the behaviour lab's labcore.py
(input_events, windows, actions; 2026-11-11). Parameters come from agentcake/data/features.json.
"""
from agentcake import datafiles

PARAMS_FILE = "data/features.json"

# Events made by the visitor's pointer, keyboard, wheel or finger. Everything else (focus, mouseover, page state,
# markers) never starts or ends a segment.
INPUT_TYPES = frozenset({"mousemove", "pointermove", "pointerdown", "pointerup", "mousedown", "mouseup", "click",
                         "wheel", "keydown", "keyup", "input", "scroll", "touchstart", "touchend", "dblclick",
                         "contextmenu", "change"})
# The first of these in a segment is when its action happens (its "act_t").
ACTION_TYPES = frozenset({"click", "wheel", "keydown", "input", "scroll", "touchstart"})
CLICK_TYPES = frozenset({"click", "dblclick", "contextmenu"})
BURST_KINDS = {"keydown": "type", "keyup": "type", "input": "type", "change": "type", "wheel": "scroll",
               "scroll": "scroll"}
MOVE_TYPES = frozenset({"mousemove", "pointermove"})


def load_params():
    """All parameters of the behaviour layer (agentcake/data/features.json), read once. Shared: copy before changing."""
    return datafiles.load(PARAMS_FILE)


def input_events(events):
    """The events that are pointer, keyboard, wheel or touch input, in their order."""
    return [e for e in events if e.get("ty") in INPUT_TYPES]


def windows(events, params=None):
    """Fixed windows of params["window_ms"] counted from the first input event; windows without input are left out.

    params: the "segments" section of features.json (default: the packaged one).
    Returns [{"start", "end", "events"}], start and end being the window's bounds in ms.
    """
    size_ms = (params or load_params()["segments"])["window_ms"]
    inputs = input_events(events)
    if not inputs:
        return []
    t0 = inputs[0]["t"]
    buckets = {}
    for e in inputs:
        buckets.setdefault(int((e["t"] - t0) // size_ms), []).append(e)
    return [{"start": t0 + k * size_ms, "end": t0 + (k + 1) * size_ms, "events": buckets[k]} for k in sorted(buckets)]


def actions(events, params=None):
    """One segment per action: a click, a typing burst or a scroll burst.

    A segment also holds the pointer movement that led up to its action (the approach), so "moves before the click"
    lives inside the click's segment. Movement that leads to no action, or that a pause longer than
    params["approach_pause_ms"] cuts off from the next action, is a segment of its own, of kind "move".

    params: the "segments" section of features.json (default: the packaged one).
    Returns [{"kind": "click" | "type" | "scroll" | "move", "events", "start", "end", "act_t"}]: start and end are
    the times of the segment's first and last event, act_t the time of its first action event (else its start).
    """
    p = params or load_params()["segments"]
    inputs = input_events(events)
    segments, approach, i = [], [], 0
    while i < len(inputs):
        e = inputs[i]
        if e["ty"] in CLICK_TYPES:
            segments.append(_segment("click", approach + [e]))
            approach, i = [], i + 1
        elif e["ty"] in BURST_KINDS:
            burst = _burst(inputs, i, p)
            segments.append(_segment(BURST_KINDS[e["ty"]], approach + burst))
            approach, i = [], i + len(burst)
        else:
            if approach and e["t"] - approach[-1]["t"] > p["approach_pause_ms"]:
                segments.append(_segment("move", approach))
                approach = []
            approach.append(e)  # moves, pointer and mouse downs and ups, touches on the way to the next action
            i += 1
    if approach:
        segments.append(_segment("move", approach))
    return segments


def _burst(inputs, first, p):
    """The typing or scroll burst that starts at inputs[first].

    Later events of the same kind join while each is at most gap_ms after the previous one; a scroll burst also takes
    pointer moves at most scroll_move_ms after it (the mouse moving while the wheel turns).
    """
    kind = BURST_KINDS[inputs[first]["ty"]]
    end = first + 1
    while end < len(inputs):
        e = inputs[end]
        gap = e["t"] - inputs[end - 1]["t"]
        same_kind = BURST_KINDS.get(e["ty"]) == kind and gap <= p["gap_ms"]
        moving_while_scrolling = (kind == "scroll" and e["ty"] in MOVE_TYPES and gap <= p["scroll_move_ms"])
        if not (same_kind or moving_while_scrolling):
            break
        end += 1
    return inputs[first:end]


def _segment(kind, events):
    act_t = next((e["t"] for e in events if e["ty"] in ACTION_TYPES), events[0]["t"])
    return {"kind": kind, "events": events, "start": events[0]["t"], "end": events[-1]["t"], "act_t": act_t}
