"""agentcake/detect/verdict_runs.py: which behaviour runs count as one side of a Human + agent session.

    python3 -I -m unittest discover -s tests -p test_verdict_runs.py -v

Made-up runs, timed in seconds: a human's run counts with enough steps over enough time, an agent's with enough clicks
or inputs of its own however fast, and its scrolling and pointer movement alone never; the reasons name each run of
the other side that does not count, with what it was counted in. The whole verdict is in test_verdict.py.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from verdict_cases import run  # noqa: E402
from agentcake.detect import verdict, verdict_runs  # noqa: E402

RULE = verdict.load_settings()["mixed"]


class LongRuns(unittest.TestCase):
    def test_a_humans_run_needs_its_steps_over_its_time(self):
        counted = run("human", 0, 30, 3, 0.1)
        typed_too_fast = run("human", 0, 0.66, 12, 0.2)  # the lab's cic-03: Claude in Chrome typing
        too_few = run("human", 0, 30, 2, 0.1)
        self.assertEqual(verdict_runs.long_runs([counted, typed_too_fast, too_few], "human", RULE), [counted])

    def test_an_agents_run_needs_its_own_clicks_or_inputs_however_fast(self):
        fast = run("agent", 0, 1, 3, 0.9)
        scrolled_and_moved = run("agent", 0, 200, 12, 0.9, acts=0)
        two_clicks = run("agent", 0, 60, 6, 0.9, acts=2)
        found = verdict_runs.long_runs([fast, scrolled_and_moved, two_clicks], "agent", RULE)
        self.assertEqual(found, [fast])

    def test_the_minimum_comes_from_the_settings(self):
        two_clicks = run("agent", 0, 60, 6, 0.9, acts=2)
        self.assertEqual(verdict_runs.long_runs([two_clicks], "agent", dict(RULE, min_actions=2)), [two_clicks])


class ShortReasons(unittest.TestCase):
    def test_each_run_of_the_other_side_that_does_not_count_says_what_it_held(self):
        runs = [run("human", 0, 30, 6, 0.1), run("agent", 31, 90, 9, 0.9, acts=1), run("human", 91, 92, 1, 0.2)]
        said = verdict_runs.short_reasons(runs, "human", RULE)
        self.assertEqual([(r["id"], r["value"]) for r in said], [("behavior.short-run", 1)])
        self.assertIn("included 1 actions", said[0]["detail"])
        self.assertEqual(verdict_runs.short_reasons(runs, "agent", RULE)[0]["value"], 1, "the human's short run")


if __name__ == "__main__":
    unittest.main()
