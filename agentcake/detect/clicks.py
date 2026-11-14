"""Which clicks show how the pointer reached them: the ones a mouse made, and among those the ones that do not repeat
the click before them in place.

Part of the behaviour layer: features.py (moves_before_click), model.py (teleport clicks) and timeline.py (the pointer
features of an action) read the approach to a click only where there is one. Input: clicks and mousemoves in the
raw-event format (segment.py). Nothing here reads the time or the network.

- mouse_click(click, press_type): not the keyboard's (detail 0), not a finger's or a pen's (after bot-signal's
  isPointerClick and agent-detector's mouse presses, MIT, ideas only: github.com/okasi/bot-signal 25a4e7b0159f,
  github.com/doubleagent-so/agent-detector a523214c3b67).
- repeats_in_place(clicks, moves, box_px): a click that lands where the click before it did, the pointer never having
  left the spot in between, shows no approach of its own: a person paging through pictures or pressing a calendar's
  arrow again, an agent pressing a button twice, a label passing its click to its input. "The same spot" is the
  square within which a browser counts a second click as one at the same place (features.json double_click_box_px:
  Chromium's MouseEvent::IsRepeatedClickEvent, 4 by 4 px, Windows' default double-click rectangle).
"""
import bisect

MOUSE = "mouse"  # protocol: PointerEvent.pointerType of a mouse
TOUCH_OR_PEN = frozenset({"touch", "pen"})  # protocol: the other PointerEvent.pointerType values
KEYBOARD_DETAIL = 0  # protocol: UI Events: a click made with the keyboard (Enter, Space) has detail 0


def mouse_click(click, press_type=None):
    """Whether a mouse made this click, so that the pointer's approach to it says something about who clicked: not
    the keyboard's (detail 0) and not a finger's or a pen's, by the click's own pointerType or, when the click names
    none (Safari's click is a MouseEvent), press_type: that of the pointerdown just before it. A click that says
    neither, as an rrweb recording's, counts as a mouse's."""
    if click.get("d") == KEYBOARD_DETAIL:
        return False
    pointer = click.get("pt")
    if pointer is None:
        pointer = press_type
    return pointer is None or pointer == MOUSE


def repeats_in_place(clicks, moves, box_px):
    """The ids of the clicks that repeat the click before them in place: they land inside the box_px square centred
    on it, and so does every move between the two (a move at the second click's own time included). How long the
    pointer rested does not matter: it made no new approach. clicks and moves: mouse clicks and mousemoves with page
    positions ("cx", "cy"), in time order."""
    move_times = [m["t"] for m in moves]
    half = box_px / 2  # protocol: the square is centred on the first click

    def near(anchor, e):
        return abs(e["cx"] - anchor["cx"]) <= half and abs(e["cy"] - anchor["cy"]) <= half

    repeated = set()
    for before, click in zip(clicks, clicks[1:]):
        between = moves[bisect.bisect_right(move_times, before["t"]):bisect.bisect_right(move_times, click["t"])]
        if near(before, click) and all(near(before, m) for m in between):
            repeated.add(id(click))
    return repeated
