"""Rebuild the raw-event format of the behaviour features from an rrweb recording.

Sessions without raw DOM events (recorded by cake 0.3.x, or PostHog-style recordings) only have rrweb. rrweb keeps
sampled mouse positions, mouse interactions, scroll positions, input lengths and page metas. It has no keydown, no
wheel, no isTrusted, hasFocus or visibility, no screenX/Y, no movementX/Y and no element boxes. The events built
here say so: trust, focus and visibility are taken as given (tr = hf = vs = 1), movement is unknown (mx = my =
None), and the features that need keys, wheels or screen positions must be read with
features.session_features(events, raw_input=False), the model's missing-data variant.

Two steps, as in our study of PostHog replays: interaction_rows() keeps the interaction events as compact rows (the
layout of its PostHog downloads), events_from_rows() turns rows into events. Ported from our own code:
the PostHog study's phcore.py (compress_rrweb, rr_to_lab, win; 2026-11-12), with one
change: a press keeps the pointer type rrweb names (phcore read every click as a mouse's). No feature reads it; the
behaviour model's mouse check does (model.mouse_pointer: a finger's slow pointer is no agent's).
"""
import itertools

INCREMENTAL = 3  # protocol: rrweb EventType.IncrementalSnapshot
META = 4  # protocol: rrweb EventType.Meta
MOUSE_MOVE = 1  # rrweb IncrementalSource.MouseMove
MOUSE_INTERACTION = 2  # protocol: rrweb IncrementalSource.MouseInteraction
SCROLL = 3  # protocol: rrweb IncrementalSource.Scroll
VIEWPORT_RESIZE = 4  # protocol: rrweb IncrementalSource.ViewportResize
INPUT = 5  # protocol: rrweb IncrementalSource.Input
TOUCH_MOVE = 6  # protocol: rrweb IncrementalSource.TouchMove
DRAG = 12  # protocol: rrweb IncrementalSource.Drag
POSITION_ROWS = {MOUSE_MOVE: "m", DRAG: "m", TOUCH_MOVE: "t"}
# rrweb MouseInteractions -> DOM event type. Focus, blur, touch-move-departed and touch-cancel are no input here.
INTERACTION_TYPES = {
    0: "mouseup",  # rrweb MouseInteractions.MouseUp
    1: "mousedown",  # rrweb MouseInteractions.MouseDown
    2: "click",  # protocol: rrweb MouseInteractions.Click
    3: "contextmenu",  # protocol: rrweb MouseInteractions.ContextMenu
    4: "dblclick",  # protocol: rrweb MouseInteractions.DblClick
    7: "touchstart",  # protocol: rrweb MouseInteractions.TouchStart
    9: "touchend",  # protocol: rrweb MouseInteractions.TouchEnd
}
# rrweb PointerTypes -> PointerEvent.pointerType. rrweb names the type on a click, and on a press whose type is not
# the one the interaction implies (a pen's mousedown); a click that names none is read as a mouse's.
POINTER_TYPES = {0: "mouse", 1: "pen", 2: "touch"}  # protocol: rrweb PointerTypes Mouse, Pen, Touch
CLICK_POINTER = POINTER_TYPES[0]
NO_COORDINATE = -1

# Row layouts by their second field. t is in ms after t0; window is the browser window the row came from (rows
# made here have None: one recording is one window; the PostHog study's downloads name it).
ROW_FIELDS = {
    "m": ("t", "row", "x", "y", "window"),  # mouse move or drag position
    "t": ("t", "row", "x", "y", "window"),  # touch move position
    "c": ("t", "row", "interaction", "x", "y", "window", "pointer_type"),
    "s": ("t", "row", "x", "y", "window", "node"),  # scroll position of a node
    "i": ("t", "row", "length", "checked", "window", "user_triggered"),  # input: text length only
    "v": ("t", "row", "width", "height", "window"),  # viewport resize
    "M": ("t", "row", "path", "kt", "window", "width", "height", "host"),  # page meta
}


def events_from_rrweb(rrweb_events):
    """rrweb events -> events in the raw-event format, in time order, with epoch-ms times."""
    return events_from_rows(interaction_rows(rrweb_events))


def interaction_rows(rrweb_events, t0=0):
    """rrweb events -> compact interaction rows (ROW_FIELDS), sorted by time. Page content (snapshots, DOM
    mutations) is left out. t0 is subtracted from every time."""
    rows = []
    for event in rrweb_events:
        t = event.get("timestamp", 0) - t0
        data = event.get("data") or {}
        if event.get("type") == INCREMENTAL:
            rows.extend(_incremental_rows(t, data))
        elif event.get("type") == META:
            rows.append([t, "M", None, None, None, data.get("width"), data.get("height"), None])
    rows.sort(key=lambda row: row[0])
    return rows


def events_from_rows(rows):
    """Compact rows -> events in the raw-event format, in time order. Each event carries the page path of its
    window's latest page row ("pg")."""
    events, page_of_window = [], {}
    for values in rows:
        row = _named(values)
        if row["row"] == "M":
            page_of_window[row["window"]] = row["path"]
            continue
        base = {"t": float(row["t"]), "tr": 1, "hf": 1, "vs": 1, "pg": page_of_window.get(row.get("window"))}
        event = _event(row, base)
        if event is not None:
            events.append(event)
    events.sort(key=lambda e: e["t"])
    return events


def _incremental_rows(t, data):
    source = data.get("source")
    if source in POSITION_ROWS:
        return [[t + (pos.get("timeOffset") or 0), POSITION_ROWS[source], round(pos.get("x", 0)),
                 round(pos.get("y", 0)), None] for pos in data.get("positions") or []]
    if source == MOUSE_INTERACTION:
        return [[t, "c", data.get("type"), _coordinate(data, "x"), _coordinate(data, "y"), None,
                 data.get("pointerType")]]
    if source == SCROLL:
        return [[t, "s", round(data.get("x") or 0), round(data.get("y") or 0), None, data.get("id")]]
    if source == VIEWPORT_RESIZE:
        return [[t, "v", data.get("width"), data.get("height"), None]]
    if source == INPUT:
        text = data.get("text")
        return [[t, "i", len(text) if isinstance(text, str) else None, data.get("isChecked"), None,
                 data.get("userTriggered")]]
    return []  # DOM mutations, media, canvas, fonts and the like: page content, not input


def _coordinate(data, axis):
    return round(data[axis]) if data.get(axis) is not None else NO_COORDINATE


def _named(values):
    """A row as a dict of its fields; fields missing at the end of a short row are None."""
    names = ROW_FIELDS.get(values[1], ("t", "row"))
    return dict(itertools.zip_longest(names, values[:len(names)]))


def _event(row, base):
    kind = row["row"]
    if kind == "m":
        return {**base, "ty": "mousemove", "cx": row["x"], "cy": row["y"], "mx": None, "my": None}
    if kind == "t":
        return {**base, "ty": "pointermove", "cx": row["x"], "cy": row["y"]}
    if kind == "c":
        ty = INTERACTION_TYPES.get(row["interaction"])
        if ty is None:
            return None
        event = {**base, "ty": ty, "cx": row["x"], "cy": row["y"]}
        if row.get("pointer_type") in POINTER_TYPES:
            event["pt"] = POINTER_TYPES[row["pointer_type"]]
        if ty == "click":
            event["d"] = 1  # rrweb keeps no detail: read as a button's click, not the keyboard's (detail 0)
            event.setdefault("pt", CLICK_POINTER)
        return event
    if kind == "s":
        return {**base, "ty": "scroll"}
    if kind == "i":
        return {**base, "ty": "input", "it": "insertText", "len": row["length"]}
    return None
