"""The lab's 25 behaviour features of a segment, and their missing variant for recordings without raw input.

Part of the behaviour layer. Input: the events of a segment (segment.py) and of its whole session,
in the raw-event format of our lab's raw.js (rrweb_events.py rebuilds it from rrweb recordings). Output: a dict of
the 25 features in FEATURES order. A feature with nothing to measure is None ("no data"), never 0; the behaviour
model reads None as "no evidence".

Ported from our own code with the same definitions and the same arithmetic, so the numbers match exactly:
the behaviour lab's labcore.py (feats, FEATURES; 2026-11-11), and the missing
variant from the PostHog study's phcore.py (blank_unobservable,
2026-11-12). One change in how, not what: the lab rescanned the whole session for every click and every scroll;
here those lookups use time indexes built once per session (SessionIndex), so a long session costs O(n log n)
instead of O(n^2). Parameters come from agentcake/data/features.json ("features", "unobservable").

Four definitions were narrowed after other projects' rules, all MIT, ideas and
thresholds only, no code copied: moves_before_click reads only a mouse's clicks (bot-signal's isPointerClick,
github.com/okasi/bot-signal 25a4e7b0159f, src/behavioral/analysis.ts); input_no_keydown reads only typed text and no
touch session (agent-detector's insertWithoutKeys, github.com/doubleagent-so/agent-detector a523214c3b67,
src/behavior/features.ts); screen_eq_client needs two places (bot-signal's cdp-input-coordinate-leak);
scroll_no_wheel also takes a finger, a held button and a release as the input behind a scroll (agent-detector's
scroll drivers, src/behavior/scroll.ts and features.ts).

The features, by group:
- pointer path (trusted mousemoves): n_move, move_rate (per second), straightness (end-to-end distance / path
  length), speed_cv (spread of the speeds / their mean), jerk_any (1 if the speed ever jumps).
- clicks: moves_before_click (mousemoves just before; only for clicks a mouse made, mouse_click(), that do not repeat
  the previous one in place, approached_clicks()), click_center_norm and click_center_px (distance from the centre of
  the clicked element: 0 in the middle, 1 on a corner; and in pixels), click_lt1px (share under a pixel),
  hover_before_click (a mouseover on the same element just before), down_up_ms (mousedown to click).
- pointer hardware: zero_movement_frac (movementX/Y both 0), screen_eq_client (screenX/Y equal clientX/Y, counted
  only when they are equal at screen_eq_min_positions different places in the session),
  pressure_zero_click (pointerdowns with pressure 0), screen_offset_jump (screen-minus-client offset changed
  between pointer events on a page, which a real mouse does not do while the window stays put).
- scroll and keys: wheel_n, scroll_no_wheel (scrolls with no wheel or key just before, no finger on the screen or
  button held down, and no release just before), keys_n, input_no_keydown
  (typed text with no keydown just before; only typed text, not a paste, an autofill, a drop or an input method's
  composition, and not in a session where a finger or a pen gave input), key_iv_cv (spread of
  the gaps between keydowns), key_burst (share of gaps too short for a hand).
- page state and timing: untrusted (events with isTrusted false), no_focus, hidden, pause_before_ms (wait since the
  previous segment ended).
"""
import bisect
import math
import statistics

from agentcake.detect import segment
from agentcake.detect.clicks import TOUCH_OR_PEN, mouse_click, repeats_in_place
from agentcake.units import MS_PER_S

FEATURES =("n_move", "move_rate", "moves_before_click", "click_center_norm", "click_center_px", "straightness",
            "speed_cv", "jerk_any", "zero_movement_frac", "screen_eq_client", "wheel_n", "scroll_no_wheel",
            "keys_n", "input_no_keydown", "key_iv_cv", "untrusted", "no_focus", "hidden", "hover_before_click",
            "down_up_ms", "pause_before_ms", "key_burst", "click_lt1px", "pressure_zero_click", "screen_offset_jump")

CORNER = math.hypot(1, 1)  # distance from the centre of a box to a corner, in half-sides
TOUCH_EVENTS = frozenset({"touchstart", "touchend"})
POINTER_POSITION_EVENTS = ("mousemove", "click", "mousedown", "pointerdown")
PRESSES = frozenset({"mousedown", "pointerdown", "touchstart"})  # a button or a finger goes down
RELEASES = frozenset({"mouseup", "pointerup", "touchend"})  # and comes up again


def session_features(events, raw_input=True, params=None):
    """Cut a session into action segments (segment.actions) and measure each one.

    events: the session's events, any order (sorted here by time, as the lab's reader did).
    raw_input: False when the events were rebuilt from an rrweb recording only (rrweb_events.py). rrweb records no
        keys, no wheel, no screen position and no movementX/Y, so the features built on them are then "no data"
        (blank_unobservable), not 0: read as-is, every scroll would look wheel-less and all typing key-less.
    params: the whole features.json (default: the packaged one).
    Returns the segments of segment.actions(), each with its "features".
    """
    p = params or segment.load_params()
    events = sorted(events, key=lambda e: e["t"])
    index = SessionIndex(events, p["features"])
    segs = segment.actions(events, p["segments"])
    prev_end = None
    for seg in segs:
        values = _features(seg["events"], index, prev_end, p["features"])
        seg["features"] = values if raw_input else blank_unobservable(values, p["unobservable"]["features"])
        prev_end = seg["end"]
    return segs


def segment_features(seg_events, session_events=None, prev_end=None, params=None):
    """The 25 features of one segment.

    session_events: the whole session (time order), where lookups before a click or a scroll may reach; default:
    the segment alone. prev_end: end time of the previous segment, for pause_before_ms. params: the "features"
    section of features.json (default: the packaged one).
    """
    p = params or segment.load_params()["features"]
    return _features(seg_events, SessionIndex(session_events or seg_events, p), prev_end, p)


def mouse_clicks(events, params=None):
    """The session's clicks a mouse made (mouse_click()), in time order. params: the "features" section of
    features.json (default: the packaged one)."""
    return SessionIndex(events, params or segment.load_params()["features"]).mouse_clicks


def approached_clicks(events, params=None):
    """The session's mouse clicks that show an approach of their own, in time order: mouse_clicks() without the ones
    that repeat the previous click in place (SessionIndex.in_place). params as for mouse_clicks()."""
    index = SessionIndex(events, params or segment.load_params()["features"])
    return [c for c in index.mouse_clicks if id(c) not in index.in_place]


def blank_unobservable(features, names=None):
    """A copy of features with the named ones set to None (missing, not false).

    names default to the "unobservable" list of features.json: the 8 features an rrweb-only recording cannot
    measure (the model's missing-data variant). The thresholds of the model stay as they are.
    """
    blank = dict(features)
    for name in names if names is not None else segment.load_params()["unobservable"]["features"]:
        blank[name] = None
    return blank


class SessionIndex:
    """Time-sorted lookups into a whole session, built once and shared by all of its segments."""

    def __init__(self, events, params):
        events = sorted(events, key=lambda e: e["t"])
        self.events, self.params = events, params
        self.move_times = _times(events, {"mousemove"})
        presses = [e for e in events if e.get("ty") == "pointerdown"]
        self.press_times, self.press_types = [e["t"] for e in presses], [e.get("pt") for e in presses]
        self.mouse_clicks = [e for e in events if e.get("ty") == "click" and self.mouse_click(e)]
        # the mouse clicks that repeat the one before them in place show no approach or aim of their own
        self.in_place = repeats_in_place([c for c in self.mouse_clicks if c.get("cx") is not None],
                                         [e for e in events if e.get("ty") == "mousemove" and e.get("cx") is not None],
                                         params["double_click_box_px"])
        # a finger or a pen gave input somewhere in the session (agent-detector's touchInput)
        self.touch_input = any(e.get("ty") in TOUCH_EVENTS or e.get("pt") in TOUCH_OR_PEN for e in events)
        # the places where the screen and the page positions of a pointer event were the same (bot-signal's
        # cdp-input-coordinate-leak, MIT, needs two: one is a window in the screen's corner)
        self.screen_equal_places = len({(e["cx"], e["cy"]) for e in events
                                        if e.get("ty") in POINTER_POSITION_EVENTS and _screen_equals_client(e)})
        self.down_times = _times(events, {"mousedown"})
        self.keydown_times = _times(events, {"keydown"})
        self.wheel_or_key_times = _times(events, {"wheel", "keydown"})
        # Each wheel or key event "covers" scrolls until this time; computed like the lab (t + window) so the
        # comparison at the edge of the window comes out the same.
        self.wheel_or_key_ends = [t + params["wheel_after_ms"] for t in self.wheel_or_key_times]
        # What else scrolls a page without a wheel (agent-detector's scroll drivers, MIT): a finger on the screen or a
        # button held on the scrollbar, and the fling or the last drag step right after its release (cake.js records
        # no touchmove, so a touch is read from its touchstart to its touchend).
        self.held_starts, self.held_ends = _held_presses(events)
        self.release_times = _times(events, RELEASES)
        self.release_ends = [t + params["wheel_after_ms"] for t in self.release_times]
        self.hover_times = {}  # target selector -> times of mouseovers on it
        self.screen_events = {}  # page -> pointer events that report both client and screen positions
        for e in events:
            if e.get("ty") == "mouseover":
                self.hover_times.setdefault(e.get("s"), []).append(e["t"])
            if e.get("ty") in ("mousemove", "mousedown", "click") and e.get("cx") is not None \
                    and e.get("sx") is not None:
                self.screen_events.setdefault(e.get("pg"), []).append(e)
        self.screen_times = {page: [e["t"] for e in evs] for page, evs in self.screen_events.items()}

    def count_moves(self, start, end):
        """Mousemoves with start <= t < end."""
        return bisect.bisect_left(self.move_times, end) - bisect.bisect_left(self.move_times, start)

    def hovered(self, selector, start, end):
        """Whether the element `selector` had a mouseover with start <= t <= end."""
        times = self.hover_times.get(selector, [])
        return bisect.bisect_right(times, end) > bisect.bisect_left(times, start)

    def last_down(self, start, end):
        """Time of the last mousedown with start <= t <= end, or None."""
        i = bisect.bisect_right(self.down_times, end)
        return self.down_times[i - 1] if i and self.down_times[i - 1] >= start else None

    def mouse_click(self, click):
        """mouse_click() with the pointer type of the last pointerdown at most down_ms before the click."""
        i = bisect.bisect_right(self.press_times, click["t"])
        recent = i and click["t"] - self.press_times[i - 1] <= self.params["down_ms"]
        return mouse_click(click, self.press_types[i - 1] if recent else None)

    def wheel_or_key_before(self, t):
        """Whether a wheel or keydown event came at most wheel_after_ms before t (or at t)."""
        first_covering = bisect.bisect_left(self.wheel_or_key_ends, t)
        return first_covering < bisect.bisect_right(self.wheel_or_key_times, t)

    def scroll_input_before(self, t):
        """Whether something other than a script moved the page at t: a wheel or a key just before, a finger or a
        button held down, or a release just before (all "just before" is wheel_after_ms)."""
        if self.wheel_or_key_before(t):
            return True
        i = bisect.bisect_right(self.held_starts, t)
        if i and t <= self.held_ends[i - 1]:
            return True
        first_covering = bisect.bisect_left(self.release_ends, t)
        return first_covering < bisect.bisect_right(self.release_times, t)

    def keydown_before(self, t):
        """Whether a keydown came at most keydown_before_ms before t (or at t)."""
        i = bisect.bisect_right(self.keydown_times, t)
        return bool(i) and t - self.keydown_times[i - 1] <= self.params["keydown_before_ms"]

    def pointer_before(self, page, t):
        """The last pointer event with screen positions on `page` before t, or None."""
        i = bisect.bisect_left(self.screen_times.get(page, []), t)
        return self.screen_events[page][i - 1] if i else None


def _features(ev, index, prev_end, p):
    values = {}
    values.update(_path_features(ev, p))
    values.update(_click_features(ev, index, p))
    values.update(_pointer_features(ev, index, p))
    values.update(_scroll_and_key_features(ev, index, p))
    values.update(_page_state_features(ev))
    values["pause_before_ms"] = (ev[0]["t"] - prev_end) if (prev_end is not None and ev) else None
    return {name: values[name] for name in FEATURES}


def _path_features(ev, p):
    moves = [e for e in ev if e["ty"] == "mousemove" and e.get("tr")]
    seconds = max(p["min_duration_s"], (ev[-1]["t"] - ev[0]["t"]) / MS_PER_S) if ev else p["min_duration_s"]
    values = {"n_move": len(moves), "move_rate": len(moves) / seconds,
              "straightness": None, "speed_cv": None, "jerk_any": None}
    if len(moves) < p["min_path_moves"]:
        return values
    steps = list(zip(moves, moves[1:]))
    path = sum(_distance(a, b) for a, b in steps)
    values["straightness"] = _distance(moves[0], moves[-1]) / path if path > 0 else None
    speeds = [_distance(a, b) / (b["t"] - a["t"]) for a, b in steps if b["t"] - a["t"] > 0]
    if len(speeds) >= p["cv_min_speeds"] and statistics.mean(speeds) > 0:
        values["speed_cv"] = statistics.pstdev(speeds) / statistics.mean(speeds)
    jumps = (abs(b - a) > p["jerk_speed_step"] for a, b in zip(speeds, speeds[1:]))
    values["jerk_any"] = 1 if len(speeds) >= p["jerk_min_speeds"] and any(jumps) else 0
    return values


def _click_features(ev, index, p):
    moves_before, centre_norm, centre_px, hovered, held = [], [], [], [], []
    for c in (e for e in ev if e["ty"] == "click"):
        if index.mouse_click(c) and id(c) not in index.in_place:  # the pointer on the spot already: no approach
            moves_before.append(index.count_moves(c["t"] - p["before_click_ms"], c["t"]))
        offset = _offset_from_centre(c)
        if offset is not None:
            centre_px.append(offset[0])
            centre_norm.append(offset[1])
        hovered.append(1 if index.hovered(c.get("s"), c["t"] - p["hover_ms"], c["t"]) else 0)
        down = index.last_down(c["t"] - p["down_ms"], c["t"])
        if down is not None:
            held.append(c["t"] - down)
    return {"moves_before_click": _mean(moves_before), "click_center_norm": _mean(centre_norm),
            "click_center_px": _mean(centre_px), "hover_before_click": _mean(hovered), "down_up_ms": _mean(held),
            "click_lt1px": _share(centre_px, lambda px: px < p["click_lt_px"])}


def _offset_from_centre(click):
    """(pixels, share of the half-diagonal) from the centre of the clicked element's box [left, top, width, height].

    Only for mouse clicks (detail > 0; a click made with the keyboard has detail 0) on a box that has a size.
    """
    box = click.get("r")
    if not box or click.get("cx") is None or (click.get("d") or 0) <= 0:
        return None
    left, top, width, height = box
    if width <= 0 or height <= 0:
        return None
    dx, dy = click["cx"] - (left + _half(width)), click["cy"] - (top + _half(height))
    return math.hypot(dx, dy), math.hypot(dx / _half(width), dy / _half(height)) / CORNER


def _half(length):
    return length / 2  # protocol: geometry, half of a side


def _pointer_features(ev, index, p):
    reporting_movement = [e for e in ev if e["ty"] in ("mousemove", "pointermove") and e.get("mx") is not None]
    pointer = [e for e in ev if e.get("cx") is not None and e["ty"] in POINTER_POSITION_EVENTS]
    leaks = index.screen_equal_places >= p["screen_eq_min_positions"]
    pointer_downs = [e for e in ev if e["ty"] == "pointerdown"]
    return {"zero_movement_frac": _share(reporting_movement, lambda e: e["mx"] == 0 and e["my"] == 0),
            "screen_eq_client": _share(pointer, lambda e: leaks and _screen_equals_client(e)),
            "pressure_zero_click": _share(pointer_downs, lambda e: (e.get("pr") or 0) == 0),
            "screen_offset_jump": _screen_offset_jump(ev, index, p)}


def _screen_offset_jump(ev, index, p):
    """Share of the segment's mousedowns and clicks whose screen-minus-client offset differs from the pointer event
    before them on the same page (the page of the segment's first event)."""
    page = ev[0].get("pg") if ev else None
    presses = [e for e in ev if e["ty"] in ("mousedown", "click") and e.get("cx") is not None
               and e.get("sx") is not None]
    if not presses or len(index.screen_events.get(page, [])) < p["offset_min_events"]:
        return None
    jumps = 0
    for e in presses:
        before = index.pointer_before(page, e["t"])
        if before is not None and _screen_offset(before) != _screen_offset(e):
            jumps += 1
    return jumps / len(presses)


def _screen_equals_client(e):
    return e.get("cx") is not None and e.get("sx") == e.get("cx") and e.get("sy") == e.get("cy")


def _screen_offset(e):
    return e["sx"] - e["cx"], e["sy"] - e["cy"]


def _scroll_and_key_features(ev, index, p):
    wheels = [e for e in ev if e["ty"] == "wheel"]
    scrolls = [e for e in ev if e["ty"] == "scroll"]
    keydowns = [e for e in ev if e["ty"] == "keydown"]
    typed = [e for e in ev if e["ty"] == "input" and e.get("it") in p["typed_input_types"] and not e.get("ic")]
    gaps = [b["t"] - a["t"] for a, b in zip(keydowns, keydowns[1:])]
    key_iv_cv = key_burst = None
    if len(keydowns) >= p["metronome_min_keys"] and gaps and statistics.mean(gaps) > 0:
        key_iv_cv = statistics.pstdev(gaps) / statistics.mean(gaps)
    if len(keydowns) >= p["burst_min_keys"] and gaps:
        key_burst = _share(gaps, lambda gap: gap < p["key_burst_ms"])
    return {"wheel_n": len(wheels) if (wheels or scrolls) else None,
            "scroll_no_wheel": _share(scrolls, lambda s: not index.scroll_input_before(s["t"])),
            "keys_n": len(keydowns) if (keydowns or typed) else None,
            "input_no_keydown": None if index.touch_input
            else _share(typed, lambda e: not index.keydown_before(e["t"])),
            "key_iv_cv": key_iv_cv, "key_burst": key_burst}


def _page_state_features(ev):
    return {"untrusted": sum(1 for e in ev if e.get("tr") == 0),
            "no_focus": _share(ev, lambda e: e.get("hf") == 0),
            "hidden": _share(ev, lambda e: e.get("vs") == 0)}


def _held_presses(events):
    """(starts, ends): when a button or a finger went down and came up again, in time order; a press that never comes
    up lasts to the end (inf). A mouse press brings a pointerdown and a mousedown, a touch a pointerdown and a
    touchstart: the first opens the press, the first release closes it."""
    starts, ends, start = [], [], None
    for e in events:
        if e.get("ty") in PRESSES and start is None:
            start = e["t"]
        elif e.get("ty") in RELEASES and start is not None:
            starts.append(start)
            ends.append(e["t"])
            start = None
    if start is not None:
        starts.append(start)
        ends.append(math.inf)
    return starts, ends


def _times(events, types):
    return [e["t"] for e in events if e.get("ty") in types]


def _distance(a, b):
    return math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])


def _mean(values):
    return statistics.mean(values) if values else None


def _share(items, test):
    """Share of items passing test, or None when there are none."""
    return sum(1 for x in items if test(x)) / len(items) if items else None
