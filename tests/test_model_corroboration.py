"""agentcake/detect/model.py: corroboration and cake's own rules (plan step S3.7, decision D36).

    python3 -I -m unittest discover -s tests -v

Without hard evidence an agent verdict needs two independent kinds of evidence (agent-detector's and HABITS' rule):
one ambiguous click approach that the HMM spreads over a short session is how people were taken for agents. The cases
on the lab's 26 sessions are kept with them, outside the published repository.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import model  # noqa: E402
from test_model import ev, hand_clicks, jump_clicks, straight_glides_and_scrolls  # noqa: E402


def scrolls_with_a_wheel(n, t0):
    """Wheel-driven scrolls, 6 s apart: action segments where no rule fires either way."""
    return [e for k in range(n) for e in (ev(t0 + 6000 * k, "wheel"), ev(t0 + 6000 * k + 10, "scroll"))]


def bare_click(t, centred=False, **fields):
    """A mouse click with no pointer move before it; on a box's centre when centred, else on no known box."""
    box = {"r": [350, 280, 100, 40]} if centred else {}
    return ev(t, "click", cx=400, cy=300, d=1, pt="mouse", **box, **fields)


class CorroborationTest(unittest.TestCase):
    """Without hard evidence an agent needs two independent kinds of evidence (plan step S3.7, D36)."""

    def test_one_kind_of_evidence_is_unsure_and_names_its_kind(self):
        result = model.judge_session([bare_click(1000)] + scrolls_with_a_wheel(3, 5000))
        self.assertEqual((result["verdict"], result["basis"]), ("unsure", []))
        self.assertEqual(result["evidence"]["one_kind"], "approach")
        self.assertGreaterEqual(result["evidence"]["agent_share"], 0.5)  # the lab's decision would have said agent

    def test_two_kinds_make_an_agent(self):
        result = model.judge_session([bare_click(1000, centred=True)] + scrolls_with_a_wheel(3, 5000))
        self.assertEqual(result["verdict"], "agent")
        self.assertEqual(result["evidence"]["agent_kinds"], ["aim", "approach"])
        self.assertNotIn("one_kind", result["evidence"])

    def test_hard_evidence_needs_no_second_kind(self):
        result = model.judge_session([bare_click(1000, tr=0)] + scrolls_with_a_wheel(3, 5000))
        self.assertEqual(result["verdict"], "agent")
        self.assertIn("untrusted", result["evidence"]["rule_hits"])

    def test_without_raw_input_evidence_on_two_actions_stands_in_for_the_second_kind(self):
        one = model.judge_session([bare_click(1000)] + scrolls_with_a_wheel(3, 5000), raw_input=False)
        two = model.judge_session([bare_click(1000), bare_click(3000)] + scrolls_with_a_wheel(3, 5000),
                                  raw_input=False)
        self.assertEqual((one["verdict"], two["verdict"]), ("unsure", "agent"))

    def test_with_raw_input_two_actions_of_one_kind_are_still_one_kind(self):
        result = model.judge_session([bare_click(1000), bare_click(3000)] + scrolls_with_a_wheel(3, 5000))
        self.assertEqual((result["verdict"], result["evidence"]["one_kind"]), ("unsure", "approach"))

    def test_the_fallback_counts_with_a_second_kind_of_evidence(self):
        events = straight_glides_and_scrolls(4)
        sparse = [dict(e, t=e["t"] + 100 * i) for i, e in enumerate(events)]
        result = model.judge_session(sparse + jump_clicks(1, t0=40000), raw_input=False)
        self.assertEqual(result["verdict"], "agent")
        self.assertIn("active_move_rate", result["basis"])
        self.assertEqual(result["evidence"]["agent_kinds"], ["aim", "approach"])

    def test_every_rule_that_says_agent_has_a_kind(self):
        params = model.load_params()
        kinds = {rule["kind"] for rule in params["rules"]["list"] if rule["weight"] > 0}
        self.assertLessEqual(kinds | set(params["fallback"]["kinds"].values()),
                             {"approach", "aim", "motion", "keys", "integrity", "scroll", "page"})


def centred_click(t):
    """A click on its box's centre after two small moves: a few moves before it and a centred aim, two kinds of
    evidence in one action, and no jump (so no teleport)."""
    return [ev(t - 40, "mousemove", cx=396, cy=298), ev(t - 20, "mousemove", cx=399, cy=300),
            ev(t, "click", cx=400, cy=300, d=1, pt="mouse", r=[350, 280, 100, 40])]


class SegmentsDecideTest(unittest.TestCase):
    """The user's rule of 11/13 (D39): segments nobody can tell count for neither side, and an agent part needs
    min_agent_actions actions that are an agent's on their own evidence."""

    def test_one_action_never_makes_an_agent_whatever_the_smoothing_pulls_along(self):
        result = model.judge_session(centred_click(1000) + scrolls_with_a_wheel(8, 5000))
        self.assertEqual([s["who"] for s in result["segments"]], ["agent"] * 9)  # the smoothing labels them all
        self.assertEqual((result["evidence"]["agent_actions"], result["verdict"]), (1, "unsure"))

    def test_enough_actions_of_their_own_make_an_agent(self):
        clicks = centred_click(1000) + centred_click(4000) + centred_click(7000)
        result = model.judge_session(clicks + scrolls_with_a_wheel(8, 12000))
        self.assertEqual((result["evidence"]["agent_actions"], result["verdict"]), (3, "agent"))

    def test_any_human_segment_makes_a_human_when_no_agent_part_stands(self):
        result = model.judge_session(centred_click(1000) + scrolls_with_a_wheel(2, 4000) + hand_clicks(3, t0=20000))
        self.assertGreater(result["evidence"]["human_share"], 0)
        self.assertEqual(result["verdict"], "human")


if __name__ == "__main__":
    unittest.main()
