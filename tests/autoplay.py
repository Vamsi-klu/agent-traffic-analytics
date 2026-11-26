"""A page that turns its own carousel: every few seconds its script presses the carousel's next button, whoever is at
the page, with element.click() or with dispatchEvent(new MouseEvent("click")). Nobody recorded these sessions: the
script's clicks are written as Chromium 149, WebKit 27.2 (Safari's engine) and Firefox 157 were measured sending them
through cake.js, every engine the same: isTrusted false, every position and the movement 0, detail 0; element.click()'s
is a PointerEvent with pointerType "" and pointerId -1, dispatchEvent's a MouseEvent with no pointer fields. The person
is beside_editor.py's, up to the moment they drag the window: six clicks by hand with the window active.

    script_clicks(t0, n, how, **fields)   the carousel's n clicks, EVERY_MS apart from t0; how: CLICK or DISPATCH;
                                          fields override the measured ones (a window without focus: hf=0)
    person()                              the person's six clicks
    still(how, **fields)                  the person clicks six times, then sits still while the carousel turns
    interleaved(how)                      the carousel turns all the time the person clicks, and after
    nobody(how)                           the carousel turning on a page nobody touches
Not a test module: discovery leaves it alone.
"""
import beside_editor

T0 = beside_editor.T0
EVERY_MS = 5000  # how often the carousel turns
TURNS = 12  # its turns after the person's last click
CLICK, DISPATCH = "click", "dispatch"
NEXT = {"s": "#carousel-next", "r": [1042, 181, 40, 40]}  # the button and its box, as recorded
SCRIPTED = {"ty": "click", "tr": 0, "hf": 1, "vs": 1, "cx": 0, "cy": 0, "sx": 0, "sy": 0, "mx": 0, "my": 0, "b": 0,
            "d": 0}
POINTER_FIELDS = {"pt": "", "pr": 0, "w": 1, "h": 1, "pid": -1, "tlx": 0, "tly": 0}  # element.click()'s PointerEvent
PERSON_UNTIL_MS = beside_editor.DRAGGED_AT_MS  # the person's clicks, before the window is dragged


def script_clicks(t0, n, how=CLICK, **fields):
    shape = {**SCRIPTED, **(POINTER_FIELDS if how == CLICK else {}), **NEXT}
    return [{**shape, **fields, "t": t0 + EVERY_MS * k} for k in range(n)]


def person():
    return [e for e in beside_editor.session() if e["t"] < T0 + PERSON_UNTIL_MS]


def still(how=CLICK, **fields):
    events = person()
    last = max(e["t"] for e in events)
    return sorted(events + script_clicks(last + EVERY_MS, TURNS, how, **fields), key=lambda e: e["t"])


def interleaved(how=CLICK):
    events = person()
    first, last = min(e["t"] for e in events), max(e["t"] for e in events)
    turns = int((last - first) // EVERY_MS) + TURNS
    return sorted(events + script_clicks(first + EVERY_MS // 2, turns, how), key=lambda e: e["t"])


def nobody(how=CLICK):
    return script_clicks(T0, TURNS, how)
