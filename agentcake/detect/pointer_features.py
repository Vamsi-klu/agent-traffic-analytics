"""The pointer-hardware features of a segment: what the pointer events themselves report, which a real mouse and an
input a script dispatched report differently.

Part of the behaviour layer, split from features.py, which measures the other features and calls measure(). Input: a
segment's events and the PointerIndex of its whole session, in the raw-event format of our lab's raw.js (segment.py).
Output: zero_movement_frac, screen_eq_client, pressure_zero_click and screen_offset_jump (features.py FEATURES), each
None when there is nothing to measure. Parameters: the "features" section of agentcake/data/features.json.

- zero_movement_frac: the share of mousemoves and pointermoves that report movementX and movementY 0. A move that
  reports none where the pointer already was, at most hover_after_scroll_ms after a wheel or a scroll, is left out:
  the browser telling the page what lies under a pointer at rest while the page scrolls under it (WebKit 27.2,
  Safari's engine, sends one 85 to 100 ms after each wheel scroll, measured; Chromium 149 and Firefox 157 send none).
- screen_eq_client: the share of pointer events whose screenX/Y equal their clientX/Y, counted only when they are
  equal at screen_eq_min_positions different places in the session (after bot-signal's cdp-input-coordinate-leak,
  MIT, github.com/okasi/bot-signal 25a4e7b0159f, the idea only: one place is a window in the screen's corner).
- pressure_zero_click: the share of pointerdowns with pressure 0.
- screen_offset_jump: the share of mousedowns and clicks whose screen-minus-client offset differs, by more than
  offset_tolerance_px, from the pointer event before them on the same page: a real mouse keeps it while the window
  stays put. Not a jump when cake.js's geometry records show the window moving by that much in between (looked for up
  to window_geo_ms after the press: cake.js records the window's place every 500 ms), nor when the next mousemove
  keeps the new offset (the page's place on the screen moved: a window dragged, DevTools opened beside the page),
  while a script's press differs from the pointer events on both sides of it. A click the keyboard made (detail 0)
  is neither a press nor the event before one: Chromium 149 and Firefox 157 give it 0 for every position (measured).
The lab's definitions (the behaviour lab's labcore.py, 2026-11-11) read every move and every press; the two narrowings
here (and no_focus's, in features.py) came in 0.6.2, after a person who scrolled and hovered the browser beside their
editor, having dragged its window, was taken for an agent (11/24).
"""
import bisect

from agentcake.detect.clicks import KEYBOARD_DETAIL
from agentcake.detect.weak import window_geometry

POINTER_POSITION_EVENTS = ("mousemove", "click", "mousedown", "pointerdown")
MOVES = frozenset({"mousemove", "pointermove"})
SCROLLS = frozenset({"wheel", "scroll"})
SCREEN_EVENTS = ("mousemove", "mousedown", "click")  # the pointer events screen_offset_jump compares


class PointerIndex:
    """Time-sorted lookups into a whole session's pointer events, built once and shared by all of its segments.
    events: the session's events in time order; params: the "features" section of features.json."""

    def __init__(self, events, params):
        self.params = params
        # the places where the screen and the page positions of a pointer event were the same
        self.screen_equal_places = len({(e["cx"], e["cy"]) for e in events
                                        if e.get("ty") in POINTER_POSITION_EVENTS and _screen_equals_client(e)})
        self.screen_events = {}  # page -> pointer events that report both client and screen positions
        for e in events:
            if _screen_positioned(e):
                self.screen_events.setdefault(e.get("pg"), []).append(e)
        self.screen_times = {page: [e["t"] for e in evs] for page, evs in self.screen_events.items()}
        self.screen_moves = {page: [e for e in evs if e["ty"] == "mousemove"]
                             for page, evs in self.screen_events.items()}
        self.screen_move_times = {page: [e["t"] for e in evs] for page, evs in self.screen_moves.items()}
        # where the window was: cake.js's geometry records (raw.js watchGeometry), on any page
        self.window_times, self.window_places = [], []
        for e in events:
            geometry = window_geometry(e)
            if geometry:
                self.window_times.append(e["t"])
                self.window_places.append(geometry[1])
        self.hover_updates = _hover_updates(events, params["hover_after_scroll_ms"])

    def pointer_before(self, page, t):
        """The last pointer event with screen positions on `page` before t, or None."""
        i = bisect.bisect_left(self.screen_times.get(page, []), t)
        return self.screen_events[page][i - 1] if i else None

    def move_after(self, page, t):
        """The first mousemove with screen positions on `page` after t, or None."""
        i = bisect.bisect_right(self.screen_move_times.get(page, []), t)
        return self.screen_moves[page][i] if i < len(self.screen_moves.get(page, [])) else None

    def window_moved(self, start, end, change):
        """Whether the window's recorded place moved by `change` (dx, dy), within offset_tolerance_px, from where it
        was at `start` to where it was recorded by window_geo_ms after `end` (a move shows at cake.js's next poll)."""
        if not self.window_times:
            return False
        before = max(bisect.bisect_right(self.window_times, start) - 1, 0)  # none yet: the first record
        after = bisect.bisect_right(self.window_times, end + self.params["window_geo_ms"]) - 1
        if after <= before:
            return False
        (x0, y0), (x1, y1) = self.window_places[before], self.window_places[after]
        return _within((x1 - x0 - change[0], y1 - y0 - change[1]), self.params["offset_tolerance_px"])


def measure(ev, index, p):
    """The four pointer-hardware features of one segment's events (see the module docstring)."""
    reporting_movement = [e for e in ev if e["ty"] in MOVES and e.get("mx") is not None
                          and id(e) not in index.hover_updates]
    pointer = [e for e in ev if e.get("cx") is not None and e["ty"] in POINTER_POSITION_EVENTS]
    leaks = index.screen_equal_places >= p["screen_eq_min_positions"]
    pointer_downs = [e for e in ev if e["ty"] == "pointerdown"]
    return {"zero_movement_frac": _share(reporting_movement, lambda e: e["mx"] == 0 and e["my"] == 0),
            "screen_eq_client": _share(pointer, lambda e: leaks and _screen_equals_client(e)),
            "pressure_zero_click": _share(pointer_downs, lambda e: (e.get("pr") or 0) == 0),
            "screen_offset_jump": _screen_offset_jump(ev, index, p)}


def _screen_offset_jump(ev, index, p):
    """Share of the segment's mousedowns and clicks whose offset jumped from the pointer event before them on the same
    page (the page of the segment's first event); None without such a press or with too few pointer events there."""
    page = ev[0].get("pg") if ev else None
    presses = [e for e in ev if e["ty"] in ("mousedown", "click") and _screen_positioned(e)]
    if not presses or len(index.screen_events.get(page, [])) < p["offset_min_events"]:
        return None
    jumps = 0
    for e in presses:
        before = index.pointer_before(page, e["t"])
        if before is not None and _offset_jumped(before, e, index, page, p):
            jumps += 1
    return jumps / len(presses)


def _offset_jumped(before, press, index, page, p):
    """Whether the press's offset jumped from the one before: it differs beyond the tolerance, the window's geometry
    records show no move by that much in between, and the next mousemove does not keep it."""
    change = _offset_change(before, press)
    if _within(change, p["offset_tolerance_px"]) or index.window_moved(before["t"], press["t"], change):
        return False
    after = index.move_after(page, press["t"])
    return after is None or not _within(_offset_change(press, after), p["offset_tolerance_px"])


def _screen_positioned(e):
    """A pointer event screen_offset_jump compares: it reports both positions, and a pointer made it."""
    return (e.get("ty") in SCREEN_EVENTS and e.get("cx") is not None and e.get("sx") is not None
            and not (e["ty"] == "click" and e.get("d") == KEYBOARD_DETAIL))


def _screen_equals_client(e):
    return e.get("cx") is not None and e.get("sx") == e.get("cx") and e.get("sy") == e.get("cy")


def _offset_change(a, b):
    """How far the screen-minus-client offset moved from event a to event b, (dx, dy)."""
    return (b["sx"] - b["cx"]) - (a["sx"] - a["cx"]), (b["sy"] - b["cy"]) - (a["sy"] - a["cy"])


def _within(change, tolerance):
    return abs(change[0]) <= tolerance and abs(change[1]) <= tolerance


def _hover_updates(events, within_ms):
    """The ids of the moves that report no movement where the pointer already was, at most within_ms after a wheel or
    a scroll. Where the pointer was is the place of the last event with a position before the move's moment: one
    pointer arrival dispatches its pointerover, mouseover, pointermove and mousemove at one moment, all at the new
    place (Claude in Chrome's move after a scroll in the lab's cic-03). events: in time order."""
    out, scrolled, moment, place, earlier = set(), None, None, None, None
    for e in events:
        if e["t"] != moment:
            moment, earlier = e["t"], place
        if e.get("ty") in SCROLLS:
            scrolled = e["t"]
        if (e.get("ty") in MOVES and e.get("mx") == 0 and e.get("my") == 0 and scrolled is not None
                and e["t"] - scrolled <= within_ms and earlier == (e.get("cx"), e.get("cy"))):
            out.add(id(e))
        if e.get("cx") is not None:
            place = (e["cx"], e.get("cy"))
    return out


def _share(items, test):
    """Share of items passing test, or None when there are none."""
    return sum(1 for x in items if test(x)) / len(items) if items else None
