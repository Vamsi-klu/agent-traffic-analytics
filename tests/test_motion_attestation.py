"""motion-attestation's 27 human captures as cake regression data (tests/motion_attestation.py; job borrow-rules, D33).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Two things are checked: the conversion keeps what upstream recorded (positions, times, key holds and gaps, touch
gestures) and adds nothing it did not record; and cake's behaviour layer, as the verdict step runs it, calls none of
these people an agent.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import motion_attestation as ma  # noqa: E402
from agentcake.detect import behavior, model  # noqa: E402

UPSTREAM_COMMIT = "bea077b307e58d7a034a75fdaf84979f438cfdd7"
CAPTURES = 27  # upstream README: "27 recorded browser sessions across Chromium, LibreWolf, desktop and touch"
KEY_TYPES = ("keydown", "keyup")
POINTER_TYPES = ("pointerdown", "pointermove", "pointerup")


def _of_type(records, *types):
    return [r for r in records if r["ty"] in types]


class FixtureTest(unittest.TestCase):
    def test_holds_upstreams_27_captures_at_the_pinned_commit(self):
        self.assertEqual(len(ma.names()), CAPTURES)
        self.assertEqual(ma.source()["commit"], UPSTREAM_COMMIT)

    def test_names_the_browser_only_where_upstream_does(self):
        browsers = [ma.capture(name)["browser"] for name in ma.names()]
        self.assertEqual(browsers.count("chromium"), 3)
        self.assertEqual(browsers.count("librewolf"), 5)
        self.assertEqual(browsers.count(None), CAPTURES - 8)

    def test_a_capture_with_touch_samples_is_a_touch_device(self):
        for name in ma.names():
            with self.subTest(name):
                self.assertEqual(ma.is_touch(name), bool(ma.capture(name)["upstream"]["tc"]))


class ConversionTest(unittest.TestCase):
    def test_stored_records_are_what_convert_makes_of_upstream(self):
        for name in ma.names():
            with self.subTest(name):
                self.assertEqual(ma.convert(ma.capture(name)["upstream"]), ma.capture(name)["raw"])

    def test_every_mouse_sample_is_a_trusted_mousemove_at_its_position_and_time(self):
        for name in ma.names():
            with self.subTest(name):
                moves = _of_type(ma.raw_events(name), "mousemove")
                self.assertEqual([[e["cx"], e["cy"], e["t"]] for e in moves], ma.capture(name)["upstream"]["m"])
                self.assertTrue(all(e["tr"] == 1 for e in moves))

    def test_fields_upstream_never_recorded_are_left_out(self):
        unrecorded = {"sx", "sy", "mx", "my", "hf", "vs", "kc", "s", "r", "d"}
        for name in ma.names():
            with self.subTest(name):
                self.assertFalse(any(unrecorded & set(e) for e in ma.raw_events(name)))

    def test_key_presses_and_releases_keep_upstreams_holds_and_gaps(self):
        for name in ma.names():
            keys = ma.capture(name)["upstream"]["k"]
            if not keys:
                continue
            with self.subTest(name):
                presses = sorted(e["t"] for e in _of_type(ma.raw_events(name), "keydown"))
                releases = sorted(e["t"] for e in _of_type(ma.raw_events(name), "keyup"))
                # upstream's arithmetic, written out: each press follows the previous release by its gap
                expected, released = [], 0
                for i, (hold, gap) in enumerate(keys):
                    pressed = 0 if i == 0 else released + gap
                    released = pressed + hold
                    expected.append((pressed, released))
                shift = presses[0] - min(p for p, _ in expected)
                self.assertEqual(presses, sorted(p + shift for p, _ in expected))
                self.assertEqual(releases, sorted(r + shift for _, r in expected))

    def test_typing_starts_after_every_other_record_so_it_is_a_stretch_of_its_own(self):
        for name in ma.names():
            records = ma.raw_events(name)
            presses = _of_type(records, "keydown")
            others = [r["t"] for r in records if r["ty"] not in KEY_TYPES]
            if presses and others:
                with self.subTest(name):
                    self.assertEqual(presses[0]["t"] - max(others), ma.KEYS_AFTER_MS)

    def test_every_touch_sample_is_one_touch_pointer_record(self):
        for name in ma.names():
            with self.subTest(name):
                pointers = _of_type(ma.raw_events(name), *POINTER_TYPES)
                self.assertEqual(len(pointers), len(ma.capture(name)["upstream"]["tc"]))
                self.assertTrue(all(p["pt"] == ma.TOUCH for p in pointers))

    def test_touch_gestures_split_on_upstreams_gap(self):
        second_gesture_t = 16 + ma.TOUCH_GESTURE_GAP_MS + 1
        samples = [[10, 10, 0.5, 4, 4, 0], [12, 30, 0.5, 4, 4, 16], [50, 50, 0.4, 3, 3, second_gesture_t]]
        records = ma.convert({"m": [], "k": [], "s": [], "tc": samples})
        self.assertEqual([r["ty"] for r in records],
                         ["touchstart", "pointerdown", "pointerup", "touchend", "touchstart", "pointerdown"])
        self.assertEqual((records[1]["pr"], records[1]["w"], records[1]["h"]), (0.5, 8, 8))

    def test_overlapping_keys_keep_upstreams_negative_gap(self):
        records = ma.convert({"m": [[0, 0, 100]], "k": [[80, 0], [70, -30]], "s": [], "tc": []})
        down = [r["t"] for r in records if r["ty"] == "keydown"]
        up = [r["t"] for r in records if r["ty"] == "keyup"]
        # the second key is pressed 30 ms before the first is released: 80 - 30 = 50 ms after the first press
        self.assertEqual(down, [100 + ma.KEYS_AFTER_MS, 100 + ma.KEYS_AFTER_MS + 50])
        self.assertEqual(up, [down[0] + 80, down[1] + 70])


class BehaviourLayerTest(unittest.TestCase):
    def test_calls_none_of_the_27_people_an_agent(self):
        for name in ma.names():
            with self.subTest(name):
                result = behavior.run(raw=ma.raw_events(name), touch=ma.is_touch(name))
                self.assertNotEqual(result["verdict"], "agent")

    def test_even_judged_on_their_few_actions_as_if_no_phone_was_seen_none_is_an_agent(self):
        # Before the M3 clean-up and borrow-rules B1, the 6 touch captures were agents here: a finger never glides
        # like a mouse, so their pointer rate read as an agent's.
        params = dict(model.load_params(), min_actions=1)
        for name in ma.names():
            with self.subTest(name):
                self.assertNotEqual(model.judge_session(ma.raw_events(name), params=params)["verdict"], "agent")


if __name__ == "__main__":
    unittest.main()
