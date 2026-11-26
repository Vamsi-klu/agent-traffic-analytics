"""A made-up session like the one taken for Human + agent on 11/24: a person who builds a website clicks around their
page, drags the browser window beside their editor, then goes on writing code and scrolls and hovers the browser
without activating it. Nobody recorded it: it is written by rule, in the raw-event format cake.js sends in its "r"
stream (docs/collect-format.md), the browser's part as WebKit 27.2 (Safari's engine) was measured sending it: 85 to
100 ms after each wheel scroll under a pointer at rest, a pointermove and a mousemove where the pointer already was,
movementX and movementY 0 (agentcake/data/features.json hover_after_scroll_ms). In a window without focus every event
reports document.hasFocus() false.

    session(t0)      the raw events, in time order
    HUMAN_CLICKS     the clicks the person made with the window active
Not a test module: discovery leaves it alone.
"""
T0 = 1_794_500_000_000  # 2026-11-12, a made-up moment
S = 1000
HUMAN_CLICKS = 6
CLICK_EVERY_MS = 12 * S
WINDOW_BEFORE, WINDOW_AFTER = (40, 60), (497, 60)  # the window's place on the screen before and after the drag
TOOLBAR = 87  # the window's height above its page, so the page's top left is the window's place plus this
DRAGGED_AT_MS = 85 * S
SCROLL_BURSTS = 6
BURST_EVERY_MS = 30 * S
FIRST_BURST_MS = 100 * S
WHEEL_TICKS = 6
TICK_MS = 120
READ_MS = 3 * S  # the pointer rests while the person reads, then the wheel turns
BURSTS_AT_REST = 3  # turns of the wheel, a read apart, before the pointer moves on
HOVER_UPDATE_MS = 95  # WebKit's move where the pointer rests, after each scroll (measured: 85 to 100 ms)
APPROACH_MOVES = 15
MOVE_MS = 40
BOX = [380, 300, 160, 40]  # the clicked buttons' box: left, top, width, height
SIZE = [1200, 700, 1200, 787]  # inner and outer width and height
SCREEN = [2, 1728, 1117]  # pixel ratio, screen width and height


def session(t0=T0):
    """The raw events, in time order."""
    events = [_geo(t0, WINDOW_BEFORE)]
    for n in range(HUMAN_CLICKS):
        events += _click(t0 + (n + 1) * CLICK_EVERY_MS, n)
    events.append(_geo(t0 + DRAGGED_AT_MS, WINDOW_AFTER))
    for n in range(SCROLL_BURSTS):
        events += _unfocused_scroll(t0 + FIRST_BURST_MS + n * BURST_EVERY_MS, n)
    return sorted(events, key=lambda e: e["t"])


def _offset(window):
    return window[0], window[1] + TOOLBAR


def _pointer(t, kind, x, y, window, focus=1, **extra):
    dx, dy = _offset(window)
    return {"t": t, "ty": kind, "tr": 1, "hf": focus, "vs": 1, "cx": x, "cy": y, "sx": x + dx, "sy": y + dy, **extra}


def _click(t, n):
    """A hand's curved approach to a button, then its press and click, with the window active."""
    left, top, width, height = BOX
    x, y = left + width // 3 + 3 * n, top + height // 3
    out = []
    for k in range(APPROACH_MOVES):
        left_to_go = APPROACH_MOVES - k
        out.append(_pointer(t - MOVE_MS * left_to_go, "mousemove", x - 9 * left_to_go, y - left_to_go ** 2 // 4,
                            WINDOW_BEFORE, mx=9, my=max(1, left_to_go // 2)))
    target = {"s": f"#cta-{n}", "r": BOX}
    out += [_pointer(t - 90, "mousedown", x, y, WINDOW_BEFORE, b=1, d=1, mx=0, my=0, **target),
            _pointer(t - 10, "mouseup", x, y, WINDOW_BEFORE, b=0, d=1, mx=0, my=0, **target),
            _pointer(t, "click", x, y, WINDOW_BEFORE, b=0, d=1, pt="mouse", mx=0, my=0, **target)]
    return out


def _unfocused_scroll(t, n):
    """The pointer glides to a new place over the window and rests there while the person reads, turning the wheel
    a few times, a read apart."""
    x, y = 500 + 40 * n, 380 - 10 * n
    glide_from = t - READ_MS - 10 * MOVE_MS
    out = [_pointer(glide_from + MOVE_MS * k, "mousemove", x - 6 * (10 - k), y - (10 - k), WINDOW_AFTER, focus=0,
                    mx=6, my=1) for k in range(11)]
    for burst in range(BURSTS_AT_REST):
        for k in range(WHEEL_TICKS):
            at = t + burst * READ_MS + k * TICK_MS
            out += [_pointer(at, "wheel", x, y, WINDOW_AFTER, focus=0, mx=0, my=0, dx=0, dy=40, dm=0),
                    {"t": at + 8, "ty": "scroll", "tr": 1, "hf": 0, "vs": 1, "y": 40 * (k + 1), "x": 0},
                    _pointer(at + HOVER_UPDATE_MS, "pointermove", x, y, WINDOW_AFTER, focus=0, mx=0, my=0,
                             pt="mouse"),
                    _pointer(at + HOVER_UPDATE_MS, "mousemove", x, y, WINDOW_AFTER, focus=0, mx=0, my=0)]
    return out


def _geo(t, window):
    return {"t": t, "ty": "geo", "why": "poll", "hf": 1, "vs": 1, "g": [*SIZE, *window, *SCREEN]}
