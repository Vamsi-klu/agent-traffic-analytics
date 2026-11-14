"""agentcake/detect/clicks.py: which clicks show how the pointer reached them.

    python3 -I -m unittest discover -s tests -v
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import clicks, segment  # noqa: E402

BOX_PX = segment.load_params()["features"]["double_click_box_px"]


def move(t, x, y):
    return {"t": float(t), "ty": "mousemove", "cx": x, "cy": y}


def click(t, x, y, **fields):
    return {"t": float(t), "ty": "click", "cx": x, "cy": y, "d": 1, **fields}


def repeated(events):
    """The indexes (in events) of the clicks repeats_in_place() finds."""
    found = clicks.repeats_in_place([e for e in events if e["ty"] == "click"],
                                    [e for e in events if e["ty"] == "mousemove"], BOX_PX)
    return [i for i, e in enumerate(events) if id(e) in found]


class MouseClickTest(unittest.TestCase):
    def test_the_keyboard_a_finger_and_a_pen_make_no_mouse_click(self):
        # Enter or Space clicks with detail 0; a tap's click names its pointer, or its pointerdown does (Safari)
        self.assertFalse(clicks.mouse_click(click(0, 1, 1, d=0)))
        self.assertFalse(clicks.mouse_click(click(0, 1, 1, pt="touch")))
        self.assertFalse(clicks.mouse_click(click(0, 1, 1), press_type="pen"))

    def test_a_mouse_or_a_click_that_names_no_pointer_is_a_mouse_click(self):
        self.assertTrue(clicks.mouse_click(click(0, 1, 1, pt="mouse")))
        self.assertTrue(clicks.mouse_click(click(0, 1, 1)))


class RepeatsInPlaceTest(unittest.TestCase):
    def test_the_square_is_the_browsers_double_click_square(self):
        # Chromium's MouseEvent::IsRepeatedClickEvent: 4 by 4 px, Windows' default double-click rectangle
        self.assertEqual(BOX_PX, 4)

    def test_a_click_on_the_spot_of_the_one_before_repeats_it(self):
        events = [move(0, 50, 50), click(100, 50, 50), click(900, 50, 50), click(1700, 52, 48)]
        self.assertEqual(repeated(events), [2, 3])

    def test_jitter_inside_the_square_keeps_the_spot(self):
        events = [click(0, 50, 50), move(300, 51, 49), move(400, 52, 52), click(800, 51, 50)]
        self.assertEqual(repeated(events), [3])

    def test_a_click_off_the_square_or_after_the_pointer_left_has_its_own_approach(self):
        off_the_square = [click(0, 50, 50), move(300, 53, 50), click(800, 53, 50)]
        left_and_back = [click(0, 50, 50), move(300, 90, 50), move(400, 50, 50), click(800, 50, 50)]
        self.assertEqual(repeated(off_the_square), [])
        self.assertEqual(repeated(left_and_back), [])

    def test_however_long_the_pointer_rests_it_makes_no_new_approach(self):
        self.assertEqual(repeated([click(0, 50, 50), click(60000, 50, 50)]), [1])

    def test_each_click_is_compared_with_the_one_just_before_it(self):
        # back on the first spot after a click elsewhere is a new approach
        events = [click(0, 50, 50), move(300, 200, 50), click(600, 200, 50), move(900, 50, 50), click(1200, 50, 50)]
        self.assertEqual(repeated(events), [])


if __name__ == "__main__":
    unittest.main()
