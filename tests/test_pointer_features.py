"""agentcake/detect/pointer_features.py: the pointer-hardware features of a segment, measured through
features.segment_features() as the behaviour model reads them.

    python3 -I -m unittest discover -s tests -p test_pointer_features.py -v

The small cases document each feature, and what a browser sends that is not the pointer's own doing: the moves WebKit
sends where a pointer rests while the page scrolls under it, a window that moved, a click the keyboard made. The cases
on the lab's 26 sessions are kept with that data, outside the published repository.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from test_features import click, ev, feats, move  # noqa: E402


def geo(t, left, top, size=(1200, 700, 1200, 787)):
    """cake.js's record of the window's geometry: inner and outer size, the window's place on the screen, the pixel
    ratio and the screen's size (raw.js watchGeometry)."""
    return {"t": float(t), "ty": "geo", "why": "poll", "hf": 1, "vs": 1, "g": [*size, left, top, 2, 1728, 1117]}


class PointerFeaturesTest(unittest.TestCase):
    def test_zero_movement_share_counts_moves_that_report_movement(self):
        self.assertEqual(feats([move(0, mx=0, my=0), move(10, mx=3, my=1), move(20)])["zero_movement_frac"], 0.5)

    def test_screen_equal_client_share(self):
        events = [move(0, 5, 5, sx=5, sy=5), move(5, 6, 6, sx=6, sy=6), click(10, 7, 7, sx=100, sy=200),
                  click(20, 9, 9, sx=100, sy=200)]
        self.assertEqual(feats(events, events)["screen_eq_client"], 0.5)

    def test_screen_equal_client_needs_two_places_in_the_session(self):
        # after bot-signal's cdp-input-coordinate-leak, MIT: one spot where the screen and the page
        # positions coincide is a window in the screen's corner, not input a debugger dispatched
        once = [move(0, 10, 10, sx=10, sy=10), move(50, 30, 10, sx=130, sy=110)]
        twice = once + [move(90, 40, 40, sx=40, sy=40)]
        self.assertEqual(feats(once, once)["screen_eq_client"], 0.0)
        self.assertEqual(feats(twice, twice)["screen_eq_client"], 2 / 3)

    def test_pressure_zero_share_of_pointerdowns(self):
        self.assertEqual(feats([ev(0, "pointerdown", pr=0), ev(10, "pointerdown", pr=0.5)])["pressure_zero_click"], 0.5)

    def test_screen_offset_jump_compares_with_the_last_pointer_event_on_the_page(self):
        session = [move(0, 10, 10, sx=110, sy=210, pg="/"), ev(100, "mousedown", cx=20, cy=20, sx=120, sy=220, pg="/"),
                   click(150, 30, 30, sx=30, sy=30, pg="/")]
        self.assertEqual(feats(session, session)["screen_offset_jump"], 0.5)

    def test_screen_offset_jump_needs_two_pointer_events_on_the_page(self):
        self.assertIsNone(feats([click(0, 1, 1, sx=1, sy=1, pg="/")])["screen_offset_jump"])

    def test_a_click_the_keyboard_made_has_no_offset_to_compare(self):
        # Enter in a field or on a button clicks with detail 0 and every position 0 (Chromium 149 and Firefox 157,
        # measured): no pointer made it, so its offset says nothing; nor is it the pointer event before the next press
        hand = [move(0, 300, 200, sx=340, sy=347), move(50, 310, 200, sx=350, sy=347)]
        enter = click(900, 0, 0, sx=0, sy=0, d=0, pt="")
        press = [ev(1500, "mousedown", cx=320, cy=210, sx=360, sy=357, d=1), click(1580, 320, 210, sx=360, sy=357, d=1)]
        session = hand + [enter] + press
        self.assertIsNone(feats([enter], session)["screen_offset_jump"])
        self.assertEqual(feats(press, session)["screen_offset_jump"], 0.0)

    def test_an_offset_the_window_move_explains_is_no_jump(self):
        # the window dragged 457 px between the last move and the press: cake.js's geometry records show it, possibly
        # only at its next poll after the press
        before = [geo(0, 40, 60), move(300, 300, 200, sx=340, sy=347)]
        dragged = [ev(5000, "mousedown", cx=300, cy=200, sx=797, sy=347, d=1),
                   click(5080, 300, 200, sx=797, sy=347, d=1)]
        for polled in (4800, 5300):
            session = before + dragged + [geo(polled, 497, 60)]
            with self.subTest(polled=polled):
                self.assertEqual(feats(dragged, session)["screen_offset_jump"], 0.0)

    def test_an_offset_the_next_move_keeps_is_no_jump(self):
        # the page's place in the window moved (DevTools opened beside it, a move the poll missed): the next move of
        # the pointer keeps the new offset
        session = [move(0, 300, 200, sx=340, sy=347), ev(3000, "mousedown", cx=300, cy=200, sx=640, sy=347, d=1),
                   click(3080, 300, 200, sx=640, sy=347, d=1), move(3500, 310, 210, sx=650, sy=357)]
        self.assertEqual(feats(session[1:3], session)["screen_offset_jump"], 0.0)

    def test_a_press_whose_offset_neither_the_window_nor_the_next_move_explains_still_jumps(self):
        # a script's click: its offset differs from the moves on both sides of it, and the window stayed where it was
        hand = [geo(0, 40, 60), move(100, 300, 200, sx=340, sy=347)]
        scripted = [click(2000, 400, 300, sx=400, sy=300, d=1)]
        session = hand + scripted + [move(2600, 305, 205, sx=345, sy=352), geo(2700, 40, 60)]
        self.assertEqual(feats(scripted, session)["screen_offset_jump"], 1.0)

    def test_a_geometry_record_whose_place_is_not_numbers_is_left_out(self):
        # the server keeps what a browser uploaded: a geometry record cake.js did not write judges as no record
        hand = [move(100, 300, 200, sx=340, sy=347)]
        scripted = [click(2000, 400, 300, sx=400, sy=300, d=1)]
        after = [move(2600, 305, 205, sx=345, sy=352)]
        for place in ((None, None), ("40", "60"), (True, 60)):
            broken = [{**geo(0, 40, 60), "g": [1200, 700, 1200, 787, *place, 2, 1728, 1117]},
                      {**geo(2700, 40, 60), "g": [1200, 700, 1200, 787, *place, 2, 1728, 1117]}]
            with self.subTest(place=place):
                session = broken[:1] + hand + scripted + after + broken[1:]
                self.assertEqual(feats(scripted, session)["screen_offset_jump"], 1.0)

    def test_an_offset_within_the_tolerance_is_no_jump(self):
        # a page zoomed from 100% shifts the offset by a pixel or so as the pointer moves between its events
        session = [move(0, 300, 200, sx=340, sy=347), click(80, 301, 200, sx=342, sy=348, d=1)]
        self.assertEqual(feats(session[1:], session)["screen_offset_jump"], 0.0)

    def test_moves_where_the_pointer_rests_after_a_scroll_report_no_movement_and_are_left_out(self):
        # WebKit 27.2 (Safari's engine, measured): 85 to 100 ms after each wheel scroll under a pointer at rest it
        # sends a pointermove and a mousemove where the pointer already was, movementX and movementY 0
        rest = (640, 400)
        events = [move(0, *rest, mx=4, my=2)]
        for t in (1000, 1120, 1240, 1360):
            events += [ev(t, "wheel", cx=rest[0], cy=rest[1], mx=0, my=0), ev(t, "scroll"),
                       ev(t + 95, "pointermove", cx=rest[0], cy=rest[1], mx=0, my=0, pt="mouse"),
                       move(t + 95, *rest, mx=0, my=0)]
        f = feats(events, events)
        self.assertEqual((f["n_move"], f["zero_movement_frac"]), (5, 0.0))

    def test_zero_movement_elsewhere_or_long_after_a_scroll_still_counts(self):
        scrolled = [move(0, 640, 400, mx=3, my=1), ev(1000, "wheel", cx=640, cy=400), ev(1000, "scroll")]
        elsewhere = scrolled + [move(1100, 700, 420, mx=0, my=0)]  # the pointer is somewhere new, movement 0
        long_after = scrolled + [move(3000, 640, 400, mx=0, my=0)]
        # Claude in Chrome after a scroll (the lab's cic-03): its pointer arrives somewhere new, the over events first,
        # all at one moment and all reporting no movement
        arrived = scrolled + [ev(1060, kind, cx=1118, cy=26, mx=0, my=0)
                              for kind in ("pointerover", "mouseover", "pointermove", "mousemove")]
        for session in (elsewhere, long_after, arrived):
            self.assertEqual(feats(session, session)["zero_movement_frac"], 2 / 3 if session is arrived else 0.5)


if __name__ == "__main__":
    unittest.main()
