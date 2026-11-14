"""agentcake/detect/arrival.py: how the pointer arrives at what it presses, and the model's session-level check that
reads it (model.py, basis "fast_arrivals").

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Made-up paths, nobody recorded them: a script that traces its path at an even pace arrives at full speed; a hand
makes a quick stroke and then homes in slowly, so its last part is slow. A session is evidence from min_fast aimed
movements on; the check holds when min_fast of them arrive fast and they are at least the share. It is one kind of
evidence (how the pointer approaches each click): alone the model is unsure, with a second kind it names an agent,
and never without raw input or without a mouse.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import arrival, model  # noqa: E402
from test_cadence import script, typed  # noqa: E402
from test_model import ev  # noqa: E402

PARAMS = model.load_params()["arrival"]
TARGET = (395, 290)  # inside the button r=[350, 280, 100, 40], off its centre
STARTS = ((100, 520), (720, 80), (60, 120), (680, 560))
EVERY_MS, STEPS = 16, 24


def even(tau):
    """A script's pace: the same distance every step, up to the target."""
    return tau


def homing(tau):
    """A hand's pace: 95% of the way in a quick smooth stroke over the first 55% of the time, the rest slowly (both
    minimum-jerk), so the last quarter moves at a few percent of the top speed."""
    smooth = lambda u: 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5  # noqa: E731
    if tau < 0.55:
        return 0.95 * smooth(tau / 0.55)
    return 0.95 + 0.05 * smooth((tau - 0.55) / 0.45)


def aimed(t0, start, pace, presses=1, pointer="mouse"):
    """A path from start to TARGET, a move every EVERY_MS ms, then a pause and a click (presses of them) that the
    pointer made."""
    out = []
    for k in range(STEPS + 1):
        f = pace(k / STEPS)
        out.append(ev(t0 + k * EVERY_MS, "mousemove", cx=round(start[0] + (TARGET[0] - start[0]) * f),
                      cy=round(start[1] + (TARGET[1] - start[1]) * f)))
    t = t0 + STEPS * EVERY_MS + 120
    for _ in range(presses):
        out += [ev(t, "mousedown", cx=TARGET[0], cy=TARGET[1]), ev(t + 90, "mouseup", cx=TARGET[0], cy=TARGET[1]),
                ev(t + 91, "click", cx=TARGET[0], cy=TARGET[1], d=1, pt=pointer, r=[350, 280, 100, 40])]
        t += 300
    return out


def session(paces, t0=1000, gap_ms=5000, pointer="mouse"):
    """One aimed movement and click per pace, gap_ms apart, from changing places."""
    out = []
    for n, pace in enumerate(paces):
        out += aimed(t0 + n * gap_ms, STARTS[n % len(STARTS)], pace, pointer=pointer)
    return out


class EndShare(unittest.TestCase):
    def test_a_path_traced_at_an_even_pace_arrives_at_full_speed(self):
        [(start, press, share)] = arrival.end_shares(aimed(1000, STARTS[0], even), PARAMS)
        self.assertGreater(share, 0.9)
        self.assertEqual((start, press), (1000, 1000 + STEPS * EVERY_MS + 120))

    def test_a_hand_slows_down_into_its_target(self):
        [(_, _, share)] = arrival.end_shares(aimed(1000, STARTS[0], homing), PARAMS)
        self.assertLess(share, PARAMS["fast_end_share"] / 2)

    def test_a_second_press_without_a_new_move_adds_nothing(self):
        self.assertEqual(len(arrival.end_shares(aimed(1000, STARTS[0], even, presses=2), PARAMS)), 1)

    def test_a_short_path_is_not_an_aimed_movement(self):
        near = (TARGET[0] - 30, TARGET[1] - 30)
        self.assertEqual(arrival.end_shares(aimed(1000, near, even), PARAMS), [])


class Judge(unittest.TestCase):
    def test_enough_fast_arrivals_hold(self):
        found = arrival.judge(session([even] * PARAMS["min_fast"]), PARAMS)
        self.assertEqual((found["holds"], found["fast"], found["movements"]),
                         (True, PARAMS["min_fast"], PARAMS["min_fast"]))
        last = 1000 + (PARAMS["min_fast"] - 1) * 5000
        self.assertEqual(found["span"], [1000, last + STEPS * EVERY_MS + 120 + 91], "first move to the last click")

    def test_fewer_movements_than_min_fast_are_no_evidence(self):
        self.assertIsNone(arrival.judge(session([even] * (PARAMS["min_fast"] - 1)), PARAMS))

    def test_fast_arrivals_under_the_share_do_not_hold(self):
        paces = [even] * PARAMS["min_fast"] + [homing] * (PARAMS["min_fast"] + 1)
        found = arrival.judge(session(paces), PARAMS)
        self.assertLess(found["share"], PARAMS["fast_share_at_least"])
        self.assertFalse(found["holds"])

    def test_the_stretch_is_where_the_fast_arrivals_gather(self):
        """A hand's six movements, then a script's ten: the stretch starts at the script's first movement."""
        paces = [homing] * 6 + [even] * 10
        found = arrival.judge(session(paces), PARAMS)
        self.assertTrue(found["holds"])
        self.assertEqual(found["span"], [1000 + 6 * 5000, 1000 + 15 * 5000 + STEPS * EVERY_MS + 120 + 91])

    def test_the_densest_run(self):
        F, S = True, False
        self.assertEqual(arrival._densest([F, S, F, F, S, S, S], 0.5, -0.5), (0, 3))
        self.assertEqual(arrival._densest([S, S, F, F, F, S, F, S, S], 0.5, -0.5), (2, 6))
        self.assertEqual(arrival._densest([S, F, F, S, F, S, S, S, S, F], 0.5, -0.5), (1, 4))
        self.assertEqual(arrival._densest([S, F, F, S, F, S, S, S, S, F], 1.0, -0.2), (1, 9), "slow ones cost less")

    def test_a_hand_never_holds(self):
        found = arrival.judge(session([homing] * 12), PARAMS)
        self.assertEqual((found["fast"], found["holds"]), (0, False))


class SessionCheck(unittest.TestCase):
    """The model's basis fast_arrivals."""

    def test_alone_it_is_one_kind_of_evidence_and_not_enough(self):
        result = model.judge_session(session([even] * PARAMS["min_fast"]))
        self.assertTrue(result["evidence"]["fast_arrivals"]["holds"])
        self.assertEqual((result["verdict"], result["evidence"]["one_kind"]), ("unsure", "approach"))

    def test_with_a_second_kind_it_makes_an_agent(self):
        events = session([even] * PARAMS["min_fast"]) + typed(script(t0=60_000))
        result = model.judge_session(events)
        self.assertEqual((result["verdict"], result["basis"]), ("agent", ["typing_cadence", "fast_arrivals"]))
        [check] = [c for c in result["timeline"]["checks"] if c["check"] == "fast_arrivals"]
        last = 1000 + (PARAMS["min_fast"] - 1) * 5000
        self.assertEqual((check["from"], check["to"]), (1000, last + STEPS * EVERY_MS + 120 + 91))
        clicks = [a for a in result["timeline"]["actions"] if a["t"] < 60_000]
        self.assertEqual({a["who"] for a in clicks}, {"agent"}, "every click in the stretch is the agent's")

    def test_never_without_raw_input(self):
        events = session([even] * PARAMS["min_fast"]) + typed(script(t0=60_000))
        self.assertNotIn("fast_arrivals", model.judge_session(events, raw_input=False)["basis"])

    def test_never_without_a_mouse(self):
        """A pen's hover moves and presses: the same paths, but no mouse drives the pointer."""
        events = session([even] * PARAMS["min_fast"], pointer="pen") + typed(script(t0=60_000))
        result = model.judge_session(events + [ev(500, "pointerdown", cx=10, cy=10, pt="pen")])
        self.assertTrue(result["evidence"]["fast_arrivals"]["holds"])
        self.assertNotIn("fast_arrivals", result["basis"])

    def test_a_hands_session_is_a_humans(self):
        result = model.judge_session(session([homing] * 12))
        self.assertEqual((result["verdict"], result["evidence"]["fast_arrivals"]["holds"]), ("human", False))


if __name__ == "__main__":
    unittest.main()
