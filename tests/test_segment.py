"""agentcake/detect/segment.py: input events, one-second windows and per-action segments.

    python3 -I -m unittest discover -s tests -v

The small cases document each rule. The cases on the lab's 26 sessions are kept with them, outside the published repository.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import segment  # noqa: E402

PARAMS = segment.load_params()["segments"]


def ev(t, ty, **fields):
    return {"t": float(t), "ty": ty, **fields}


def shape(segs):
    return [(s["kind"], s["start"], s["end"], len(s["events"])) for s in segs]


class InputEventsTest(unittest.TestCase):
    def test_only_pointer_key_scroll_and_touch_events_are_input(self):
        events = [ev(0, "focus"), ev(1, "mouseover"), ev(2, "geo"), ev(3, "mousemove"), ev(4, "keyup"),
                  ev(5, "touchend"), ev(6, "visibility"), ev(7, "change")]
        self.assertEqual([e["ty"] for e in segment.input_events(events)], ["mousemove", "keyup", "touchend", "change"])


class WindowsTest(unittest.TestCase):
    def test_windows_start_at_the_first_input_event(self):
        events = [ev(50, "focus"), ev(100, "mousemove"), ev(900, "click"), ev(1100, "mousemove")]
        wins = segment.windows(events, PARAMS)
        self.assertEqual([(w["start"], w["end"], len(w["events"])) for w in wins],
                         [(100.0, 1100.0, 2), (1100.0, 2100.0, 1)])

    def test_windows_without_input_are_left_out(self):
        wins = segment.windows([ev(0, "mousemove"), ev(3500, "mousemove")], PARAMS)
        self.assertEqual([w["start"] for w in wins], [0.0, 3000.0])

    def test_no_input_means_no_windows(self):
        self.assertEqual(segment.windows([ev(0, "focus")], PARAMS), [])

    def test_window_length_comes_from_the_parameters(self):
        wins = segment.windows([ev(0, "mousemove"), ev(600, "mousemove")], {**PARAMS, "window_ms": 500})
        self.assertEqual([w["start"] for w in wins], [0.0, 500.0])


class ActionsTest(unittest.TestCase):
    def test_a_click_holds_the_pointer_approach_before_it(self):
        segs = segment.actions([ev(0, "mousemove"), ev(100, "mousedown"), ev(200, "click")], PARAMS)
        self.assertEqual(shape(segs), [("click", 0.0, 200.0, 3)])
        self.assertEqual(segs[0]["act_t"], 200.0)

    def test_a_pause_over_two_seconds_ends_the_approach(self):
        segs = segment.actions([ev(0, "mousemove"), ev(2500, "mousemove"), ev(2600, "click")], PARAMS)
        self.assertEqual(shape(segs), [("move", 0.0, 0.0, 1), ("click", 2500.0, 2600.0, 2)])

    def test_keys_and_inputs_close_together_are_one_typing_burst(self):
        events = [ev(0, "keydown"), ev(5, "input"), ev(60, "keyup"), ev(1200, "keydown"), ev(2500, "keydown")]
        self.assertEqual(shape(segment.actions(events, PARAMS)),
                         [("type", 0.0, 1200.0, 4), ("type", 2500.0, 2500.0, 1)])

    def test_moves_during_a_scroll_gesture_join_the_scroll(self):
        segs = segment.actions([ev(0, "scroll"), ev(150, "mousemove"), ev(400, "wheel")], PARAMS)
        self.assertEqual(shape(segs), [("scroll", 0.0, 400.0, 3)])

    def test_a_move_after_the_scroll_gesture_starts_the_next_approach(self):
        segs = segment.actions([ev(0, "wheel"), ev(300, "mousemove"), ev(400, "click")], PARAMS)
        self.assertEqual(shape(segs), [("scroll", 0.0, 0.0, 1), ("click", 300.0, 400.0, 2)])

    def test_moves_after_the_last_action_are_a_move_segment(self):
        segs = segment.actions([ev(0, "click"), ev(100, "mousemove"), ev(200, "pointermove")], PARAMS)
        self.assertEqual(shape(segs), [("click", 0.0, 0.0, 1), ("move", 100.0, 200.0, 2)])

    def test_the_action_time_is_the_first_action_event_not_the_approach(self):
        segs = segment.actions([ev(0, "mousemove"), ev(50, "keyup"), ev(100, "keydown")], PARAMS)
        self.assertEqual((segs[0]["kind"], segs[0]["start"], segs[0]["act_t"]), ("type", 0.0, 100.0))

    def test_a_segment_without_an_action_event_acts_at_its_start(self):
        segs = segment.actions([ev(10, "mousemove"), ev(20, "mousemove")], PARAMS)
        self.assertEqual(segs[0]["act_t"], 10.0)

    def test_events_that_are_not_input_are_ignored(self):
        self.assertEqual(segment.actions([ev(0, "focus"), ev(5, "mouseover")], PARAMS), [])

    def test_the_burst_gap_comes_from_the_parameters(self):
        events = [ev(0, "keydown"), ev(500, "keydown")]
        self.assertEqual(len(segment.actions(events, {**PARAMS, "gap_ms": 100})), 2)

    def test_the_events_are_not_changed(self):
        events = [ev(0, "mousemove"), ev(100, "click")]
        before = [dict(e) for e in events]
        segment.actions(events, PARAMS)
        self.assertEqual(events, before)

    def test_without_parameters_the_packaged_ones_are_used(self):
        events = [ev(0, "mousemove"), ev(2500, "mousemove"), ev(2600, "click")]
        self.assertEqual(shape(segment.actions(events)), shape(segment.actions(events, PARAMS)))


if __name__ == "__main__":
    unittest.main()
