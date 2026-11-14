"""Made-up sessions in the shape of a PostHog replay download (plan step S1.5 tests).

No real data: hashes, times and pages are invented. Row layouts follow the download's compressed rrweb rows:
page [t, "M", path, kt, window, width, height, host], move [t, "m", x, y, window], click
[t, "c", type, x, y, window, pointer], scroll [t, "s", x, y, window, id], input [t, "i", length, checked, window, user].
"""
import datetime as dt
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

T0 = 1_700_000_000_000  # an arbitrary session start, epoch ms
CLICK = 2  # rrweb MouseInteractions.Click
FOCUS = 5  # rrweb MouseInteractions.Focus
MOUSE_DOWN = 1  # rrweb MouseInteractions.MouseDown


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()[:19]


def page(t, path="/", kt=None, window="w1"):
    return [t, "M", path, kt, window, 1280, 800, "example.test"]


def move(t, x=10, y=10, window="w1"):
    return [t, "m", x, y, window]


def touch_move(t, x=10, y=10, window="w1"):
    return [t, "t", x, y, window]


def click(t, x=10, y=10, window="w1", kind=CLICK):
    return [t, "c", kind, x, y, window, None]


def scroll(t, y=100, window="w1"):
    return [t, "s", 0, y, window, 1]


def typed(t, length=3, window="w1"):
    return [t, "i", length, None, window, True]


def props(os_name="Mac", browser="Chrome", chrome_major="150", device_type="Desktop", browser_type="browser",
          botscent_type="human", headless=False):
    return {"browser_type": browser_type, "botscent_type": botscent_type, "device_type": device_type,
            "ua": {"os": os_name, "browser": browser, "chrome_major": chrome_major, "headless": headless}}


def session(h, rows, owner=False, start_ms=T0, **prop_values):
    rows = sorted(rows, key=lambda r: r[0])
    last = rows[-1][0] if rows else 0
    return {"h": h, "is_top_person": owner, "start_ms": start_ms, "start": iso(start_ms) + "Z",
            "duration_s": round(last / 1000), "active_s": 0, "props": props(**prop_values), "rr": rows}


def agent_window(start_ms, end_ms):
    return {"start_ms": start_ms, "end_ms": end_ms, "start": iso(start_ms), "n_calls": 1}


def browse(t0, n_clicks=3, window="w1"):
    """A few human-looking clicks, each after a short curved approach, starting at t0 (ms after session start)."""
    rows, t = [], t0
    for i in range(n_clicks):
        for k in range(12):
            rows.append(move(t, 100 + 7 * k + i, 200 + (k * k) % 9, window))
            t += 40
        rows.append(click(t + 30, 190 + i, 205, window))
        t += 2600
    return rows
