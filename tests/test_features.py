"""agentcake/detect/features.py: the lab's 25 behaviour features and their missing variant (plan step S3.6).

    python3 -I -m unittest discover -s tests -v

The small cases document each feature. The cases on the lab's 26 sessions and on PostHog replays are kept with that
data, outside the published repository.
"""
import math
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import features, segment  # noqa: E402

MEDIAN_TOLERANCE = 0.0005 + 1e-9
FLOAT_TOLERANCE = 1e-12
LAB_FEATURES = ("n_move", "move_rate", "moves_before_click", "click_center_norm", "click_center_px", "straightness",
                "speed_cv", "jerk_any", "zero_movement_frac", "screen_eq_client", "wheel_n", "scroll_no_wheel",
                "keys_n", "input_no_keydown", "key_iv_cv", "untrusted", "no_focus", "hidden", "hover_before_click",
                "down_up_ms", "pause_before_ms", "key_burst", "click_lt1px", "pressure_zero_click",
                "screen_offset_jump")
NOTE_12_UNOBSERVABLE = {"keys_n", "key_iv_cv", "key_burst", "input_no_keydown", "wheel_n", "scroll_no_wheel",
                        "screen_eq_client", "zero_movement_frac"}


def ev(t, ty, **fields):
    return {"t": float(t), "ty": ty, "tr": 1, "hf": 1, "vs": 1, **fields}


def move(t, x=0, y=0, **fields):
    return ev(t, "mousemove", cx=x, cy=y, **fields)


def click(t, x=0, y=0, **fields):
    return ev(t, "click", cx=x, cy=y, **fields)


def feats(events, session=None, prev_end=None):
    return features.segment_features(events, session, prev_end)


class FeatureListTest(unittest.TestCase):
    def test_the_25_lab_features_in_the_lab_order(self):
        self.assertEqual(features.FEATURES, LAB_FEATURES)

    def test_every_segment_gets_all_25(self):
        self.assertEqual(tuple(feats([move(0), click(100)])), LAB_FEATURES)


class ClickFeaturesTest(unittest.TestCase):
    BOX = [0, 0, 100, 50]

    def test_moves_before_click_counts_moves_in_the_last_1500_ms(self):
        events = [move(0), move(1000), move(1400), click(1600)]
        self.assertEqual(feats(events, events)["moves_before_click"], 2)

    def test_a_click_the_keyboard_made_has_no_approach(self):
        # borrow-rules B3 (bot-signal's isPointerClick): Enter or Space on a button clicks with detail 0
        self.assertIsNone(feats([click(1000, d=0)])["moves_before_click"])

    def test_a_click_a_finger_or_a_pen_made_has_no_approach(self):
        # borrow-rules B3: by the click's own pointerType, or, where the click names none (Safari), the pointerdown's
        pressed = [ev(900, "pointerdown", cx=0, cy=0, pt="pen"), click(1000, d=1)]
        self.assertIsNone(feats([click(1000, d=1, pt="touch")])["moves_before_click"])
        self.assertIsNone(feats(pressed, pressed)["moves_before_click"])

    def test_a_mouse_click_keeps_its_approach(self):
        events = [ev(900, "pointerdown", cx=0, cy=0, pt="mouse"), click(1000, d=1, pt="mouse")]
        self.assertEqual(feats(events, events)["moves_before_click"], 0)

    def test_click_centre_is_0_in_the_middle_and_1_on_a_corner(self):
        middle = feats([click(0, 50, 25, d=1, r=self.BOX)])
        corner = feats([click(0, 100, 50, d=1, r=self.BOX)])
        self.assertEqual((middle["click_center_norm"], middle["click_center_px"], middle["click_lt1px"]),
                         (0.0, 0.0, 1.0))
        self.assertEqual((corner["click_center_norm"], corner["click_lt1px"]), (1.0, 0.0))
        self.assertAlmostEqual(corner["click_center_px"], math.hypot(50, 25))

    def test_click_centre_needs_a_mouse_click_on_a_box(self):
        for c in (click(0, 50, 25, d=0, r=self.BOX), click(0, 50, 25, d=1), click(0, 50, 25, d=1, r=[0, 0, 0, 50])):
            with self.subTest(click=c):
                f = feats([c])
                self.assertEqual((f["click_center_norm"], f["click_center_px"], f["click_lt1px"]), (None, None, None))

    def test_hover_before_click_looks_for_a_mouseover_on_the_same_target_within_5_s(self):
        session = [ev(0, "mouseover", s="#buy"), click(4000, s="#buy"), click(4100, s="#other"), click(5500, s="#buy")]
        self.assertAlmostEqual(feats(session, session)["hover_before_click"], 1 / 3)

    def test_down_up_ms_is_the_time_from_the_last_mousedown(self):
        session = [ev(1000, "mousedown"), ev(1050, "mousedown"), click(1080)]
        self.assertEqual(feats(session, session)["down_up_ms"], 30.0)

    def test_without_clicks_there_are_no_click_features(self):
        f = feats([move(0), move(10)])
        names = ("moves_before_click", "click_center_norm", "hover_before_click", "down_up_ms", "click_lt1px")
        self.assertEqual([f[n] for n in names], [None] * len(names))


class PathFeaturesTest(unittest.TestCase):
    def test_a_straight_steady_path(self):
        f = feats([move(0, 0), move(10, 10), move(20, 20), move(30, 30)])
        self.assertEqual((f["n_move"], f["move_rate"], f["straightness"], f["speed_cv"], f["jerk_any"]),
                         (4, 4.0, 1.0, 0.0, 0))

    def test_a_speed_jump_is_jerk(self):
        self.assertEqual(feats([move(0, 0), move(10, 10), move(20, 40), move(30, 50)])["jerk_any"], 1)

    def test_a_curved_path_is_less_straight(self):
        f = feats([move(0, 0, 0), move(10, 10, 0), move(20, 10, 10)])
        self.assertAlmostEqual(f["straightness"], math.sqrt(0.5))

    def test_only_trusted_moves_count_and_path_features_need_3(self):
        f = feats([move(0, 0), move(10, 10), move(20, 20, tr=0)])
        self.assertEqual((f["n_move"], f["straightness"], f["speed_cv"], f["jerk_any"]), (2, None, None, None))

    def test_move_rate_is_per_second_over_at_least_one_second(self):
        self.assertEqual(feats([move(0), move(1000), move(2000)])["move_rate"], 1.5)


class PointerFeaturesTest(unittest.TestCase):
    def test_zero_movement_share_counts_moves_that_report_movement(self):
        self.assertEqual(feats([move(0, mx=0, my=0), move(10, mx=3, my=1), move(20)])["zero_movement_frac"], 0.5)

    def test_screen_equal_client_share(self):
        events = [move(0, 5, 5, sx=5, sy=5), move(5, 6, 6, sx=6, sy=6), click(10, 7, 7, sx=100, sy=200),
                  click(20, 9, 9, sx=100, sy=200)]
        self.assertEqual(feats(events, events)["screen_eq_client"], 0.5)

    def test_screen_equal_client_needs_two_places_in_the_session(self):
        # borrow-rules B5 (bot-signal's cdp-input-coordinate-leak, MIT): one spot where the screen and the page
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


class ScrollAndKeyFeaturesTest(unittest.TestCase):
    def test_a_scroll_within_400_ms_after_a_wheel_or_key_is_not_scroll_without_wheel(self):
        session = [ev(800, "wheel"), ev(1000, "scroll"), ev(3000, "scroll"), ev(4300, "keydown"), ev(4600, "scroll")]
        f = feats(session, session)
        self.assertEqual((f["wheel_n"], f["scroll_no_wheel"]), (1, 1 / 3))

    def test_a_scroll_during_a_touch_or_a_held_button_has_its_input(self):
        # borrow-rules B6 (agent-detector's scroll drivers, MIT): a finger on the screen, a button held on the
        # scrollbar, and the fling right after either, scroll the page with no wheel
        touch = [ev(0, "touchstart"), ev(300, "scroll"), ev(600, "scroll"), ev(900, "touchend"), ev(1200, "scroll")]
        drag = [ev(0, "mousedown", cx=1, cy=1), ev(500, "scroll"), ev(1500, "scroll"), ev(1600, "mouseup", cx=1, cy=1)]
        for session in (touch, drag):
            self.assertEqual(feats(session, session)["scroll_no_wheel"], 0.0)

    def test_a_scroll_long_after_any_input_still_has_none(self):
        session = [ev(0, "mousedown", cx=1, cy=1), ev(50, "mouseup", cx=1, cy=1), ev(2000, "scroll")]
        self.assertEqual(feats(session, session)["scroll_no_wheel"], 1.0)

    def test_no_wheel_and_no_scroll_means_no_scroll_features(self):
        f = feats([move(0)])
        self.assertEqual((f["wheel_n"], f["scroll_no_wheel"]), (None, None))

    def test_input_within_150_ms_after_a_keydown_has_its_key(self):
        session = [ev(0, "keydown"), ev(100, "input", it="insertText"), ev(1000, "input", it="insertText"),
                   ev(1100, "input", it="deleteContentBackward")]
        f = feats(session, session)
        self.assertEqual((f["keys_n"], f["input_no_keydown"]), (1, 0.5))

    def test_typed_text_without_any_keydown_reads_zero_keys(self):
        f = feats([ev(0, "input", it="insertText")])
        self.assertEqual((f["keys_n"], f["input_no_keydown"]), (0, 1.0))

    def test_only_typed_text_can_lack_its_keydown(self):
        # borrow-rules B4 (agent-detector's insertWithoutKeys, MIT): a paste from the menu, an autofill or a
        # correction, a drop and an input method's composition change a field without a keydown, and humans make them
        for change in ({"it": "insertFromPaste"}, {"it": "insertReplacementText"}, {"it": "insertFromDrop"},
                       {"it": "insertText", "ic": 1}):
            f = feats([ev(0, "input", **change)])
            self.assertEqual((f["keys_n"], f["input_no_keydown"]), (None, None), change)

    def test_typed_text_after_a_touch_has_no_missing_keydown(self):
        # borrow-rules B4: an on-screen keyboard, handwriting or dictation on a touch screen types without keys
        for pointer in ("touch", "pen"):
            session = [ev(0, "pointerdown", cx=1, cy=1, pt=pointer), ev(500, "input", it="insertText")]
            self.assertIsNone(feats(session[1:], session)["input_no_keydown"], pointer)

    def test_steady_typing_has_no_spread_and_no_burst(self):
        f = feats([ev(t, "keydown") for t in (0, 100, 200, 300)])
        self.assertEqual((f["key_iv_cv"], f["key_burst"]), (0.0, 0.0))

    def test_keys_under_8_ms_apart_are_a_burst_and_spread_needs_3_keys(self):
        self.assertAlmostEqual(feats([ev(t, "keydown") for t in (0, 5, 10, 200)])["key_burst"], 2 / 3)
        f = feats([ev(0, "keydown"), ev(5, "keydown")])
        self.assertEqual((f["key_iv_cv"], f["key_burst"]), (None, 1.0))


class PageStateAndTimingTest(unittest.TestCase):
    def test_untrusted_count_and_no_focus_and_hidden_shares(self):
        f = feats([ev(0, "mousemove", tr=0), ev(10, "click", hf=0), ev(20, "scroll", vs=0), ev(30, "keydown")])
        self.assertEqual((f["untrusted"], f["no_focus"], f["hidden"]), (1, 0.25, 0.25))

    def test_pause_before_is_the_wait_since_the_previous_segment(self):
        self.assertEqual(feats([click(500)], prev_end=200.0)["pause_before_ms"], 300.0)
        self.assertIsNone(feats([click(500)])["pause_before_ms"])

    def test_click_lookups_reach_into_the_whole_session(self):
        session = [move(1000), move(1400), click(1600)]
        self.assertEqual(feats(session[-1:], session)["moves_before_click"], 2)
        self.assertEqual(feats(session[-1:])["moves_before_click"], 0)

    def test_the_events_are_not_changed(self):
        session = [move(0, 1, 1, mx=0, my=0), click(100, 1, 1, d=1, r=[0, 0, 2, 2], s="#a")]
        before = [dict(e) for e in session]
        features.session_features(session)
        self.assertEqual(session, before)


class SessionFeaturesTest(unittest.TestCase):
    def test_each_action_segment_gets_its_features_and_its_pause(self):
        segs = features.session_features([move(0), click(100), ev(3000, "scroll"), ev(9000, "keydown")])
        self.assertEqual([(s["kind"], s["features"]["pause_before_ms"]) for s in segs],
                         [("click", None), ("scroll", 2900.0), ("type", 6000.0)])

    def test_with_raw_input_scrolls_without_wheels_and_text_without_keys_are_evidence(self):
        segs = features.session_features([ev(0, "scroll"), ev(100, "input", it="insertText")])
        f_scroll, f_type = segs[0]["features"], segs[1]["features"]
        self.assertEqual((f_scroll["wheel_n"], f_scroll["scroll_no_wheel"]), (0, 1.0))
        self.assertEqual((f_type["keys_n"], f_type["input_no_keydown"]), (0, 1.0))

    def test_without_raw_input_the_8_unobservable_features_have_no_data(self):
        segs = features.session_features([ev(0, "scroll"), ev(100, "input", it="insertText")], raw_input=False)
        for seg in segs:
            for name in NOTE_12_UNOBSERVABLE:
                self.assertIsNone(seg["features"][name], name)


class MissingVariantTest(unittest.TestCase):
    def test_the_unobservable_list_is_note_12s_8_features(self):
        self.assertEqual(set(segment.load_params()["unobservable"]["features"]), NOTE_12_UNOBSERVABLE)

    def test_blank_unobservable_turns_them_into_no_data_and_keeps_the_rest(self):
        f = feats([ev(0, "scroll"), move(10, mx=0, my=0)])
        blank = features.blank_unobservable(f)
        for name in NOTE_12_UNOBSERVABLE:
            self.assertIsNone(blank[name], name)
        self.assertEqual({n: blank[n] for n in f if n not in NOTE_12_UNOBSERVABLE},
                         {n: f[n] for n in f if n not in NOTE_12_UNOBSERVABLE})
        self.assertEqual((f["wheel_n"], f["zero_movement_frac"]), (0, 1.0))  # the input is left as it was

    def test_blank_unobservable_takes_its_own_list(self):
        self.assertEqual(features.blank_unobservable({"a": 0, "b": 0}, ["a"]), {"a": None, "b": 0})


if __name__ == "__main__":
    unittest.main()
