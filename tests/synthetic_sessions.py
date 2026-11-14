"""Made-up sessions for the tests whose point is not who recorded them (the behaviour lab's recordings
are not published). Nobody recorded these: they are written by rule, in
the raw-event format cake.js sends in its "r" stream (docs/collect-format.md) and in rrweb's events, the way an
automated browser drives a page through the DevTools protocol: one mouse move straight onto the middle of each target,
the click a few milliseconds later, and a field typed a key every millisecond.

    agent_raw(t0)      the raw events of CLICKS clicks, each followed by a typed field, in time order
    agent_rrweb(t0)    the same visit as rrweb records it: a meta event, then mouse moves, clicks and inputs
Not a test module: discovery leaves it alone.
"""
T0 = 1_794_500_000_000  # 2026-11-12, a made-up moment
CLICKS = 8
STEP_MS = 4_000  # from one click to the next
PRESS_MS = 9  # the move, the press and the release are this far apart, as a script dispatches them
TYPED_KEYS = 12  # keys typed into the field after each click, one a millisecond
FIRST_TYPE_MS = 500  # from the click to the first key
TARGET = (180, 36)  # the width and height of every made-up button
PAGE = "/task"
VIEWPORT = {"width": 1280, "height": 800}
RRWEB_META, RRWEB_INCREMENTAL = 4, 3  # rrweb EventType
RRWEB_MOVE, RRWEB_INTERACTION, RRWEB_INPUT = 1, 2, 5  # rrweb IncrementalSource
RRWEB_DOWN, RRWEB_UP, RRWEB_CLICK = 1, 0, 2  # rrweb MouseInteractions


def targets():
    """[(selector, left, top, centre x, centre y)] of the made-up buttons, one under the other."""
    width, height = TARGET
    out = []
    for n in range(CLICKS):
        left, top = 100 + 40 * n, 120 + 70 * n
        out.append((f"#step-{n}", left, top, left + width // 2, top + height // 2))
    return out


def _pointer(t, kind, x, y, **extra):
    return {"t": t, "ty": kind, "tr": 1, "hf": 1, "vs": 1, "cx": x, "cy": y, "sx": x, "sy": y, "mx": 0, "my": 0,
            "pg": PAGE, **extra}


def agent_raw(t0=T0):
    """The raw events, in time order."""
    events = [{"t": t0, "ty": "visibility", "vs": 1, "hf": 1, "pg": PAGE}]
    width, height = TARGET
    for n, (selector, left, top, x, y) in enumerate(targets()):
        t = t0 + STEP_MS * (n + 1)
        rect = {"s": selector, "r": [left, top, width, height]}
        events += [_pointer(t, "mousemove", x, y, b=0, d=0),
                   _pointer(t + PRESS_MS, "mousedown", x, y, b=1, d=1, **rect),
                   _pointer(t + 2 * PRESS_MS, "mouseup", x, y, b=0, d=1, **rect),
                   _pointer(t + 2 * PRESS_MS, "click", x, y, b=0, d=1, pt="mouse", **rect)]
        for key in range(TYPED_KEYS):
            at = t + FIRST_TYPE_MS + key
            events += [{"t": at, "ty": "keydown", "tr": 1, "hf": 1, "vs": 1, "kc": "letter", "ce": 0, "rp": 0,
                        "pg": PAGE, **rect},
                       {"t": at, "ty": "input", "tr": 1, "hf": 1, "vs": 1, "it": "insertText", "ic": 0, "pg": PAGE,
                        **rect}]
    return events


def agent_rrweb(t0=T0):
    """The same visit as rrweb's events, in time order."""
    events = [{"type": RRWEB_META, "data": {"href": "https://shop.example" + PAGE, **VIEWPORT}, "timestamp": t0}]
    for n, (_, _, _, x, y) in enumerate(targets()):
        t, node = t0 + STEP_MS * (n + 1), n + 1

        def incremental(at, source, **data):
            return {"type": RRWEB_INCREMENTAL, "data": {"source": source, **data}, "timestamp": at}
        events += [incremental(t, RRWEB_MOVE, positions=[{"x": x, "y": y, "id": node, "timeOffset": 0}]),
                   incremental(t + PRESS_MS, RRWEB_INTERACTION, type=RRWEB_DOWN, id=node, x=x, y=y),
                   incremental(t + 2 * PRESS_MS, RRWEB_INTERACTION, type=RRWEB_UP, id=node, x=x, y=y),
                   incremental(t + 2 * PRESS_MS, RRWEB_INTERACTION, type=RRWEB_CLICK, id=node, x=x, y=y),
                   incremental(t + FIRST_TYPE_MS + TYPED_KEYS, RRWEB_INPUT, text="*" * TYPED_KEYS,
                               isChecked=False, id=node)]
    return events
