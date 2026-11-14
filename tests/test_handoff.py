"""agentcake/detect/handoff.py: where the actor changed between a session's timeline runs.

    python3 -I -m unittest discover -s tests -p test_handoff.py -v

Made-up steps and runs: a hand-off is at the new actor's first action (a click, a key or typed input, a wheel), a run
with no action of its own hands nothing over, and the steps the smoothing left unsure between two actors go to the side
their own scores make likeliest. The cases through timeline.build() are in test_timeline.py and test_timeline_turns.py.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import handoff, timeline  # noqa: E402

LIMIT = timeline.load_params()["timeline"]["logit_limit"]


def step(t, who, score, kind="click", start=None, first=None):
    """A timeline step as build() makes it: its moment, its first event, where its activity began, who and score."""
    return {"kind": kind, "t": t, "first": t if first is None else first, "start": t if start is None else start,
            "who": who, "p": score, "score": score}


class Handoffs(unittest.TestCase):
    def test_the_steps_nobody_can_tell_between_two_actors_are_split_where_their_own_scores_are_likeliest(self):
        steps = [step(1000, "agent", 0.99), step(2000, "agent", 0.99), step(3000, "unsure", 0.6),
                 step(4000, "unsure", 0.55), step(5000, "unsure", 0.2, start=4600), step(6000, "unsure", 0.3),
                 step(7000, "human", 0.01), step(8000, "human", 0.01)]
        runs = timeline.runs(steps)
        clicks = [s["t"] for s in steps]
        found = handoff.handoffs(runs, steps, clicks, LIMIT)
        self.assertEqual([(h["from"], h["to"], h["t"], h["after"]) for h in found], [("agent", "human", 5000, 2000)])
        self.assertEqual([h["t"] for h in handoff.handoffs(runs)], [7000], "without the steps: the new run's start")

    def test_a_split_with_nothing_to_choose_between_keeps_the_new_runs_start(self):
        steps = [step(1000, "human", 0.01), step(2000, "agent", 0.99, start=1500), step(3000, "agent", 0.99)]
        runs = timeline.runs(steps)
        self.assertEqual([h["t"] for h in handoff.handoffs(runs, steps, [1000, 2000, 3000], LIMIT)], [2000])

    def test_the_hand_off_is_the_new_sides_first_action_not_its_approach(self):
        steps = [step(1000, "agent", 0.99), step(5000, "human", 0.01, kind="input", start=3000, first=4100)]
        runs = timeline.runs(steps)
        # the person's pointer sets off at 3000, the first key goes down at 4000, the field changes at 4100
        self.assertEqual([h["t"] for h in handoff.handoffs(runs, steps, [1000, 4000, 4100, 5000], LIMIT)], [4000])

    def test_a_run_with_no_action_of_its_own_hands_nothing_over(self):
        steps = [step(1000, "agent", 0.99), step(2000, "agent", 0.99), step(3000, "human", 0.1, kind="move"),
                 step(4000, "agent", 0.99)]
        runs = timeline.runs(steps)
        self.assertEqual(handoff.handoffs(runs, steps, [1000, 2000, 4000], LIMIT), [])
        with self.assertRaises(ValueError):
            handoff.handoffs(runs, steps, [1000, 2000, 4000])

    def test_timeline_still_offers_the_same_function(self):
        self.assertIs(timeline.handoffs, handoff.handoffs)


if __name__ == "__main__":
    unittest.main()
