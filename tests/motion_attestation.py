"""motion-attestation's 27 recorded human captures, in cake's raw-event format, as regression data.

github.com/libcaptcha/motion-attestation (MIT, Copyright (c) 2026 libcaptcha), commit bea077b307e5
(test/fixtures/humans/*.json): 27 sessions of real people moving a mouse, touching a screen, typing and scrolling in
Chromium and LibreWolf, desktop and touch. Upstream keeps them as real captures only ("never add a generated human").
tests/fixtures/motion_attestation/humans.json holds each capture twice: as upstream wrote it (`upstream`, unchanged)
and converted to the records cake.js sends in its `r` stream (`raw`, docs/collect-format.md), so the behaviour layer
reads them like any recorded visit. Used by tests/test_motion_attestation.py (job borrow-rules, plan decision D33).

Upstream's collector (src/collector.js at that commit) records less than cake.js, and the converted records hold only
what it recorded:
- m [x, y, t]: a mousemove at clientX x, clientY y, t ms after the collector started. Upstream records no screen
  position, movementX/Y, buttons or focus, so those fields are left out (the features read them as "no data").
- tc [x, y, force, radiusX, radiusY, t]: touchstart, touchmove and touchend samples, their type not kept. A gap of more
  than TOUCH_GESTURE_GAP_MS starts a new gesture (upstream's own split, analyzer.js gestures()); in cake.js's terms a
  gesture's first sample is a touchstart and a pointerdown, its last (when it has two or more) a pointerup and a
  touchend, the ones between pointermoves. Pointer records carry pointerType "touch", the position, pressure = force
  and contact width and height = twice the radii (PointerEvent's contact geometry); touch records carry no position,
  as cake.js sends them.
- k [hold, gap]: per released key, how long it was held and the time from the previous release to its press (0 for
  the first key). Upstream never records when typing happened, only these intervals, and never which key. The keys
  become keydown and keyup records whose holds and gaps are exactly upstream's (overlapping keys included), placed
  as one typing stretch whose first press comes KEYS_AFTER_MS after the capture's last pointer, touch or scroll
  sample (or at KEYS_AFTER_MS when there is none): far enough apart that the typing is a segment of its own. No key
  class (kc): the key is not known.
- s [scrollY, delta, t]: a scroll record at that scrollY.
- c (clicks), ev (event order), sensors and engagement are not in upstream's fixtures, so there are no clicks.
Every record is isTrusted (tr 1): these are a real browser's own events, and upstream keeps real captures only.
Times count from the capture's start (upstream's clock), not from the epoch: they are only compared with each other.

Rebuild the fixture from a download of the repository at that commit (only if upstream's captures change):

    python3 -I tests/motion_attestation.py <motion-attestation folder>/test/fixtures/humans
"""
import functools
import json
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "motion_attestation"
FIXTURE_FILE = "humans.json"
SOURCE = {"repository": "github.com/libcaptcha/motion-attestation",
          "commit": "bea077b307e58d7a034a75fdaf84979f438cfdd7",
          "path": "test/fixtures/humans/",
          "licence": "MIT, Copyright (c) 2026 libcaptcha (LICENSE.motion-attestation in this folder)"}

TOUCH_GESTURE_GAP_MS = 100  # upstream analyzer.js gestures(points, gapMs = 100)
# Longer than the 1.2 s that ends a typing burst and the 2 s pause that ends an approach (agentcake/data/features.json
# "segments"), so the rebuilt typing never joins the pointer movement before it.
KEYS_AFTER_MS = 3000
PAGE = "/"  # upstream records no page; one capture is one page
TOUCH = "touch"
BROWSERS = ("chromium", "librewolf")  # named in upstream's widget-<browser>-<n>.json file names
MOUSE_X, MOUSE_Y, MOUSE_T = 0, 1, 2  # protocol: upstream m sample [x, y, t]
TOUCH_X, TOUCH_Y, TOUCH_FORCE, TOUCH_RX, TOUCH_RY, TOUCH_T = 0, 1, 2, 3, 4, 5  # protocol: upstream tc sample
KEY_HOLD, KEY_GAP = 0, 1  # protocol: upstream k sample [dwell, flight]
SCROLL_Y, SCROLL_T = 0, 2  # protocol: upstream s sample [scrollY, delta, t]


@functools.lru_cache(maxsize=None)
def _fixture():
    with open(FIXTURE_DIR / FIXTURE_FILE, encoding="utf-8") as f:
        return json.load(f)


def source():
    """Where the captures come from: {"repository", "commit", "path", "licence"}."""
    return _fixture()["source"]


def names():
    """The 27 capture names (upstream's file names without .json), in upstream's order."""
    return [capture["name"] for capture in _fixture()["captures"]]


def capture(name):
    """One capture: {"name", "browser", "device", "upstream", "raw"} (see the module docstring)."""
    return next(c for c in _fixture()["captures"] if c["name"] == name)


def raw_events(name):
    """The capture's records in cake's raw-event format, in time order."""
    return sorted(capture(name)["raw"], key=lambda e: e["t"])


def is_touch(name):
    """Whether the capture came from a touch screen (it has touch samples): cake treats it as a phone or tablet."""
    return capture(name)["device"] == TOUCH


def convert(upstream):
    """cake raw records for one upstream capture (see the module docstring), in time order."""
    records = [_mousemove(sample) for sample in upstream.get("m") or []]
    for gesture in _gestures(upstream.get("tc") or []):
        records += _touch_gesture(gesture)
    records += [{"t": sample[SCROLL_T], "ty": "scroll", "tr": 1, "y": sample[SCROLL_Y], "pg": PAGE}
                for sample in upstream.get("s") or []]
    last = max((r["t"] for r in records), default=0)
    records += _keys(upstream.get("k") or [], last + KEYS_AFTER_MS)
    return sorted(records, key=lambda r: r["t"])


def describe(name, upstream):
    """The fixture entry for one upstream file: its browser (from the file name), device and both forms."""
    browser = next((b for b in BROWSERS if f"-{b}-" in name), None)
    return {"name": name, "browser": browser, "device": TOUCH if upstream.get("tc") else "desktop",
            "upstream": upstream, "raw": convert(upstream)}


def _mousemove(sample):
    return {"t": sample[MOUSE_T], "ty": "mousemove", "tr": 1, "cx": sample[MOUSE_X], "cy": sample[MOUSE_Y],
            "pg": PAGE}


def _gestures(samples):
    """Touch samples split on gaps longer than TOUCH_GESTURE_GAP_MS, in time order."""
    gestures, current = [], []
    for sample in sorted(samples, key=lambda s: s[TOUCH_T]):
        if current and sample[TOUCH_T] - current[-1][TOUCH_T] > TOUCH_GESTURE_GAP_MS:
            gestures.append(current)
            current = []
        current.append(sample)
    return gestures + ([current] if current else [])


def _touch_gesture(gesture):
    first, last = gesture[0], gesture[-1]
    records = [{"t": first[TOUCH_T], "ty": "touchstart", "tr": 1, "pg": PAGE}, _pointer("pointerdown", first)]
    records += [_pointer("pointermove", sample) for sample in gesture[1:-1]]
    if len(gesture) > 1:
        records += [_pointer("pointerup", last), {"t": last[TOUCH_T], "ty": "touchend", "tr": 1, "pg": PAGE}]
    return records


def _pointer(event_type, sample):
    return {"t": sample[TOUCH_T], "ty": event_type, "tr": 1, "cx": sample[TOUCH_X], "cy": sample[TOUCH_Y],
            "pt": TOUCH, "pr": sample[TOUCH_FORCE], "w": 2 * sample[TOUCH_RX], "h": 2 * sample[TOUCH_RY],
            "pg": PAGE}


def _key_times(samples):
    """(press, release) per upstream [hold, gap] pair, counted from the first press.

    Upstream pushes a pair when a key is released: press = previous release + gap (negative when keys overlap),
    release = press + hold. The first pair's gap has no previous release and is not used.
    """
    times, released = [], None
    for sample in samples:
        pressed = 0 if released is None else released + sample[KEY_GAP]
        released = pressed + sample[KEY_HOLD]
        times.append((pressed, released))
    return times


def _keys(samples, start):
    """keydown and keyup records from upstream's pairs, the earliest press at `start`."""
    times = _key_times(samples)
    shift = start - min((pressed for pressed, _ in times), default=0)
    records = []
    for pressed, released in times:
        records += [{"t": pressed + shift, "ty": "keydown", "tr": 1, "pg": PAGE},
                    {"t": released + shift, "ty": "keyup", "tr": 1, "pg": PAGE}]
    return records


def build(upstream_dir):
    """The fixture from upstream's test/fixtures/humans folder: every capture, upstream's file order (sorted)."""
    files = sorted(Path(upstream_dir).glob("*.json"))
    captures = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            captures.append(describe(path.stem, json.load(f)))
    return {"source": SOURCE, "captures": captures}


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    fixture = build(argv[1])
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_DIR / FIXTURE_FILE, "w", encoding="utf-8") as f:
        json.dump(fixture, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print(f"{len(fixture['captures'])} captures -> {FIXTURE_DIR / FIXTURE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
